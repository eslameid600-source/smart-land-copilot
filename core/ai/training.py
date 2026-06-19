"""
خط أنابيب تدريب نموذج TFT — معالجة بيانات زمنية كاملة
=========================================================
Smart Land Management Copilot — TFT Training Pipeline
=====================================================

المكونات:
  1. معالجة البيانات الزمنية باستخدام Pandas (Normalization, Windowing, Splitting)
  2. دالة train_tft_model() الشاملة مع Early Stopping
  3. مجموعات بيانات PyTorch (Dataset/DataLoader)
  4. تقييم النموذج ومقاييس الأداء
  5. حفظ/تحميل النموذج

التركيب: pip install torch pandas numpy scikit-learn
التشغيل: python -c "from core.ai.tft.training import train_tft_model; print('جاهز')"
"""

import os
import json
import math
import logging
import time
from typing import Optional, Dict, List, Tuple, Any, Union
from datetime import datetime

import numpy as np
import pandas as pd
import torch

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 1. معالجة البيانات الزمنية باستخدام Pandas
# ════════════════════════════════════════════════════════════════

class TimeSeriesPreprocessor:
    """
    معالج البيانات الزمنية للأراضي العقارية المصرية
    ─────────────────────────────────────────────────
    يحوّل بيانات الأسعار الخام إلى نوافذ تدريب/تنبؤ جاهزة لنموذج TFT.

    الميزات:
        - تطبيع (Normalization) بالـ MinMax و Standard
        - إنشاء نوافذ زمنية (Sliding Windows)
        - استخراج الميزات الزمنية (الشهر، الموسم، يوم الأسبوع)
        - تقسيم التدريب/الاختبار (Train/Test Split) الزمني
        - معالجة القيم المفقودة (Forward Fill + Interpolation)
        - توليد بيانات تجريبية لأغراض العرض

    مثال الاستخدام:
        >>> preprocessor = TimeSeriesPreprocessor()
        >>> df = preprocessor.generate_sample_data()
        >>> dataset = preprocessor.prepare_for_tft(df, target_col="السعر_للمتر")
    """

    # أسماء المحافظات المصرية مع ترميز رقمي
    GOVERNORATE_ENCODING: Dict[str, int] = {
        "القاهرة": 1, "الجيزة": 2, "الإسكندرية": 3, "6 أكتوبر": 4,
        "العاصمة الإدارية": 5, "السويس": 6, "الإسماعيلية": 7,
        "بورسعيد": 8, "دمياط": 9, "الدقهلية": 10, "المنوفية": 11,
        "الغربية": 12, "كفر الشيخ": 13,
    }

    # أنواع النشاط مع ترميز رقمي
    ACTIVITY_ENCODING: Dict[str, int] = {
        "سكني": 1, "تجاري": 2, "صناعي": 3, "زراعي": 4, "لوجستي": 5,
    }

    def __init__(
        self,
        encoder_length: int = 24,
        decoder_length: int = 12,
        target_col: str = "السعر_للمتر",
        date_col: str = "التاريخ",
        batch_size: int = 32,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
    ):
        self.encoder_length = encoder_length
        self.decoder_length = decoder_length
        self.target_col = target_col
        self.date_col = date_col
        self.batch_size = batch_size
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio

        # أدوات التطبيع — تُحفظ لتطبيقها لاحقاً
        self.scalers: Dict[str, Any] = {}
        self.feature_columns: List[str] = []
        self.observed_columns: List[str] = []
        self.known_future_columns: List[str] = []
        self.static_columns: List[str] = []
        self.target_mean: float = 0.0
        self.target_std: float = 1.0

    # ────────────────────────────────────────────
    # 1.1 توليد بيانات تجريبية
    # ────────────────────────────────────────────

    def generate_sample_data(
        self,
        num_months: int = 72,
        num_lands: int = 5,
        seed: int = 42,
    ):
        """
        توليد بيانات أسعار أراضٍ تجريبية لمحاكاة السوق المصري.

        يُنتج بيانات شهرية لعدة أراضٍ مع:
          - اتجاهات تصاعدية واقعية
          - تقلبات موسمية
          - ضوضاء عشوائية
          - أحداث مفاجئة (صدمات السوق)

        المعاملات:
            num_months : عدد الأشهر (افتراضي: 72 = 6 سنوات)
            num_lands  : عدد الأراضي (افتراضي: 5)
            seed       : بذرة عشوائية

        المخرجات:
            pd.DataFrame بالأعمدة: التاريخ, land_id, المحافظة, النشاط,
                                    المساحة_متر, المرافق, السعر_للمتر, إجمالي_السعر
        """
        pd  # confirm pandas is available

        np.random.seed(seed)
        governorates = list(self.GOVERNORATE_ENCODING.keys())[:num_lands]
        activities = ["سكني", "تجاري", "صناعي", "لوجستي", "زراعي"]

        # أسعار أساسية لكل محافظة (جنيه/متر مربع)
        base_prices = {
            "القاهرة": 3500, "الجيزة": 2800, "الإسكندرية": 4200,
            "6 أكتوبر": 2500, "العاصمة الإدارية": 5000,
            "السويس": 1200, "الإسماعيلية": 1800,
        }

        # معدلات النمو السنوي (%)
        growth_rates = {
            "القاهرة": 0.12, "الجيزة": 0.10, "الإسكندرية": 0.11,
            "6 أكتوبر": 0.15, "العاصمة الإدارية": 0.18,
            "السويس": 0.14, "الإسماعيلية": 0.13,
        }

        records = []
        start_date = pd.Timestamp("2019-01-01")

        for i, gov in enumerate(governorates):
            activity = activities[i % len(activities)]
            area = np.random.uniform(500, 5000)  # متر مربع
            utilities = np.random.randint(1, 5)    # 1-4 مرافق
            base = base_prices.get(gov, 2000)
            growth = growth_rates.get(gov, 0.08)

            for m in range(num_months):
                date = start_date + pd.DateOffset(months=m)

                # الاتجاه الأساسي (تراكمي)
                trend = base * ((1 + growth / 12) ** m)

                # الموسمية: أسعار أعلى في الصيف والربيع
                month = date.month
                seasonality = 1.0 + 0.05 * math.sin(2 * math.pi * (month - 3) / 12)

                # صدمات عشوائية (أحداث السوق)
                if np.random.random() < 0.05:
                    shock = np.random.uniform(0.8, 1.3)
                else:
                    shock = 1.0

                # الضوضاء
                noise = np.random.normal(1.0, 0.03)

                price = trend * seasonality * shock * noise
                price = max(price, 100)  # حد أدنى

                records.append({
                    self.date_col: date,
                    "land_id": f"EG-{gov[:3].upper()}-{i + 1:02d}",
                    "المحافظة": gov,
                    "النشاط": activity,
                    "المساحة_متر": round(area, 1),
                    "المرافق": utilities,
                    "السعر_للمتر": round(price, 2),
                    "إجمالي_السعر": round(price * area, 2),
                    "معدل_النمو_الشهري": round(growth / 12, 4),
                })

        df = pd.DataFrame(records)
        df[self.date_col] = pd.to_datetime(df[self.date_col])

        logger.info(
            f"تم توليد بيانات تجريبية: {len(df)} سجل, "
            f"{df['land_id'].nunique()} أرض, "
            f"{df[self.date_col].min().strftime('%Y-%m')} → "
            f"{df[self.date_col].max().strftime('%Y-%m')}"
        )

        return df

    # ────────────────────────────────────────────
    # 1.2 معالجة القيم المفقودة
    # ────────────────────────────────────────────

    def handle_missing_values(
        self,
        df: "pd.DataFrame",
        method: str = "ffill_interpolate",
    ) -> "pd.DataFrame":
        """
        معالجة القيم المفقودة في البيانات الزمنية.

        الاستراتيجيات:
            - "ffill_interpolate": تعبئة أمامية ثم استكمال خطي
            - "ffill": تعبئة أمامية فقط
            - "interpolate": استكمال خطي فقط
            - "drop": حذف الصفوف الفارغة

        المعاملات:
            df     : DataFrame المدخل
            method : اسم الاستراتيجية

        المخرجات:
            DataFrame نظيف
        """
        pd  # confirm pandas is available
        df = df.copy()

        missing_before = df.isnull().sum().sum()

        numeric_cols = df.select_dtypes(include=[np.number]).columns

        if method == "ffill_interpolate":
            # لكل أرض على حدة (لمنع تسرب البيانات بين الأراضي)
            for col in numeric_cols:
                df[col] = df.groupby("land_id", group_keys=False)[col].apply(
                    lambda x: x.ffill().interpolate(method="linear")
                )
        elif method == "ffill":
            df[numeric_cols] = df[numeric_cols].ffill()
        elif method == "interpolate":
            df[numeric_cols] = df[numeric_cols].interpolate(method="linear")
        elif method == "drop":
            df = df.dropna(subset=numeric_cols)

        missing_after = df.isnull().sum().sum()

        if missing_before > 0:
            logger.info(
                f"معالجة القيم المفقودة: {missing_before} → {missing_after} "
                f"(الطريقة: {method})"
            )

        return df

    # ────────────────────────────────────────────
    # 1.3 استخراج الميزات الزمنية
    # ────────────────────────────────────────────

    def extract_time_features(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """
        استخراج ميزات زمنية من عمود التاريخ.

        الميزات المُستخرجة:
            - شهر (1-12) — متغير مستقبلي معروف
            - ربع سنة (1-4) — متغير مستقبلي معروف
            - سنة — متغير مستقبلي معروف
            - يوم_من_بداية_السنة (1-365) — متغير مستقبلي معروف
            - هل_نهاية_السنة (0/1) — مؤشر موسمي

        المعاملات:
            df : DataFrame يحتوي على عمود التاريخ

        المخرجات:
            DataFrame مع أعمدة الميزات الزمنية المضافة
        """
        pd  # confirm pandas is available
        df = df.copy()

        dt = df[self.date_col].dt

        df["شهر"] = dt.month.astype(float)
        df["ربع_سنة"] = dt.quarter.astype(float)
        df["سنة"] = dt.year.astype(float)
        df["يوم_من_بداية_السنة"] = dt.dayofyear.astype(float)

        # مؤشر نهاية السنة (يونيو-أغسطس = موسم الذروة)
        df["هل_نهاية_السنة"] = (df["شهر"].isin([6, 7, 8])).astype(float)

        # ترميز الموسم
        season_map = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 0}
        df["الموسم"] = df["شهر"].map(season_map).astype(float)

        logger.info(f"تم استخراج 6 ميزات زمنية من عمود التاريخ")

        return df

    # ────────────────────────────────────────────
    # 1.4 التطبيع (Normalization)
    # ────────────────────────────────────────────

    def fit_scalers(self, df: "pd.DataFrame"):
        """
        حساب معاملات التطبيع لكل عمود رقمي.
        يُحفظ المتوسط والانحراف المعياري للتطبيق على بيانات جديدة.
        """
        pd  # confirm pandas is available

        numeric_cols = [
            c for c in df.select_dtypes(include=[np.number]).columns
            if c != self.target_col
        ]

        for col in numeric_cols:
            self.scalers[col] = {
                "mean": float(df[col].mean()),
                "std": float(df[col].std()) + 1e-8,
                "min": float(df[col].min()),
                "max": float(df[col].max()) + 1e-8,
            }

        # تطبيع خاص للهدف (السعر) — Log Transform + Standard
        self.target_mean = float(np.log1p(df[self.target_col]).mean())
        self.target_std = float(np.log1p(df[self.target_col]).std()) + 1e-8

        logger.info(
            f"تم حساب معاملات التطبيع لـ {len(self.scalers)} عمود. "
            f"هدف (log): متوسط={self.target_mean:.4f}, انحراف={self.target_std:.4f}"
        )

    def apply_scaling(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """تطبيق التطبيع المحفوظ على DataFrame."""
        df = df.copy()

        for col, params in self.scalers.items():
            if col in df.columns:
                # Z-score normalization
                df[col] = (df[col] - params["mean"]) / params["std"]

        # Log transform + Z-score للسعر
        if self.target_col in df.columns:
            df[self.target_col] = (
                np.log1p(df[self.target_col]) - self.target_mean
            ) / self.target_std

        return df

    def inverse_transform_target(self, scaled_values: np.ndarray) -> np.ndarray:
        """
        عكس التطبيع للقيم المستهدفة.
        يُستخدم لتحويل تنبؤات النموذج إلى أسعار حقيقية بالجنيه.

        المعاملات:
            scaled_values : مصفوفة القيم المُطبَّعة

        المخرجات:
            مصفوفة الأسعار الحقيقية
        """
        # عكس Z-score
        unscaled = scaled_values * self.target_std + self.target_mean
        # عكس Log Transform
        real_values = np.expm1(unscaled)
        return real_values

    # ────────────────────────────────────────────
    # 1.5 إنشاء النوافذ الزمنية (Sliding Windows)
    # ────────────────────────────────────────────

    def create_windows(
        self,
        df: "pd.DataFrame",
        land_id: Optional[str] = None,
    ) -> Dict[str, np.ndarray]:
        """
        إنشاء نوافذ انزلاقية من بيانات السلاسل الزمنية.

        كل نافذة تتكون من:
            - encoder_inputs  : آخر encoder_length خطوات (الماضي)
            - decoder_targets : decoder_length خطوات التالية (المستقبل — الأهداف)
            - decoder_known   : ميزات مستقبلية معروفة لفترة التنبؤ

        المعاملات:
            df      : DataFrame مُطبَّع ومُعالج
            land_id : معرف أرض محدد (اختياري — يأذن بفلتر)

        المخرجات:
            dict {
                "observed_encoder":   (num_windows, encoder_length, observed_dim),
                "known_future_encoder": (num_windows, encoder_length, future_dim),
                "observed_decoder":   (num_windows, decoder_length, observed_dim),
                "known_future_decoder": (num_windows, decoder_length, future_dim),
                "targets":            (num_windows, decoder_length, 1),
                "static_continuous":  (num_windows, static_dim),
                "static_categorical": dict {name: (num_windows,)},
                "land_ids":           list[str],
            }
        """
        pd  # confirm pandas is available

        if land_id:
            df = df[df["land_id"] == land_id].copy()

        # ترتيب بالتاريخ لكل أرض
        df = df.sort_values([self.date_col, "land_id"]).reset_index(drop=True)

        # تحديد أعمدة كل نوع متغير
        observed_cols = [self.target_col, "معدل_النمو_الشهري"]
        known_future_cols = ["شهر", "ربع_سنة", "الموسم", "هل_نهاية_السنة", "يوم_من_بداية_السنة"]
        static_cont_cols = ["المساحة_متر", "المرافق"]

        # تصفية الأعمدة الموجودة فعلاً
        observed_cols = [c for c in observed_cols if c in df.columns]
        known_future_cols = [c for c in known_future_cols if c in df.columns]
        static_cont_cols = [c for c in static_cont_cols if c in df.columns]

        self.observed_columns = observed_cols
        self.known_future_columns = known_future_cols
        self.static_columns = static_cont_cols

        # النافذة الكلية: encoder + decoder
        total_window = self.encoder_length + self.decoder_length

        # جمع البيانات لكل أرض على حدة
        all_windows = {
            "observed_encoder": [],
            "known_future_encoder": [],
            "observed_decoder": [],
            "known_future_decoder": [],
            "targets": [],
            "static_continuous": [],
            "static_categorical": {},
            "land_ids": [],
        }

        # تهيئة قوائم المتغيرات الفئوية الثابتة
        for cat_col in ["المحافظة", "النشاط"]:
            if cat_col in df.columns:
                all_windows["static_categorical"][cat_col] = []

        for lid, group in df.groupby("land_id"):
            group = group.sort_values(self.date_col).reset_index(drop=True)

            if len(group) < total_window:
                continue  # بيانات غير كافية لهذه الأرض

            # تحويل الأعمدة المرغوبة إلى numpy
            obs_data = group[observed_cols].values if observed_cols else np.zeros((len(group), 0))
            known_data = group[known_future_cols].values if known_future_cols else np.zeros((len(group), 0))

            # القيم المستهدفة (نفس target_col)
            target_data = group[self.target_col].values

            # المتغيرات الثابتة
            static_cont = group[static_cont_cols].values[0] if static_cont_cols else np.array([])

            # إنشاء النوافذ المنزلقة
            num_possible = len(group) - total_window + 1

            for i in range(num_possible):
                enc_start = i
                enc_end = i + self.encoder_length
                dec_start = enc_end
                dec_end = dec_start + self.decoder_length

                # مدخلات المشفر
                all_windows["observed_encoder"].append(obs_data[enc_start:enc_end])
                all_windows["known_future_encoder"].append(known_data[enc_start:enc_end])

                # مدخلات فك التشفير
                # المتغيرات المُلاحظة في فترة التنبؤ: الصفر للأجزاء المستقبلية
                dec_observed = np.zeros_like(obs_data[dec_start:dec_end])
                dec_observed[:, 0] = 0.0  # السعر غير معروف مستقبلاً
                if obs_data.shape[1] > 1:
                    dec_observed[:, 1:] = obs_data[dec_start:dec_end, 1:]
                all_windows["observed_decoder"].append(dec_observed)

                all_windows["known_future_decoder"].append(known_data[dec_start:dec_end])

                # الأهداف
                all_windows["targets"].append(target_data[dec_start:dec_end].reshape(-1, 1))

                # المتغيرات الثابتة
                all_windows["static_continuous"].append(static_cont)

                # المتغيرات الفئوية
                for cat_col in all_windows["static_categorical"]:
                    encoding = self.GOVERNORATE_ENCODING.get(
                        group[cat_col].iloc[0], 0
                    ) if cat_col == "المحافظة" else self.ACTIVITY_ENCODING.get(
                        group[cat_col].iloc[0], 0
                    )
                    all_windows["static_categorical"][cat_col].append(encoding)

                all_windows["land_ids"].append(lid)

        # تحويل القوائم إلى مصفوفات numpy
        result = {}
        for key, val in all_windows.items():
            if key == "static_categorical":
                result[key] = {
                    k: np.array(v, dtype=np.int64) for k, v in val.items()
                }
            elif key == "land_ids":
                result[key] = val
            elif val:
                arr = np.array(val, dtype=np.float32)
                # إضافة بُعد إذا كانت الأعمدة = 0
                if arr.ndim == 1:
                    arr = arr.reshape(-1, 1)
                result[key] = arr
            else:
                result[key] = np.array([], dtype=np.float32).reshape(0, 0)

        total_windows = len(all_windows["land_ids"])
        logger.info(
            f"تم إنشاء {total_windows} نافذة تدريب "
            f"(encoder={self.encoder_length}, decoder={self.decoder_length})"
        )

        return result

    # ────────────────────────────────────────────
    # 1.6 تقسيم التدريب/الاختبار الزمني
    # ────────────────────────────────────────────

    def temporal_train_val_test_split(
        self, windows: Dict[str, np.ndarray]
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray]]:
        """
        تقسيم النوافذ زمنياً إلى تدريب + تحقق + اختبار.

        يُحافظ على الترتيب الزمني (لا يوجد تسرب من المستقبل للماضي).

        المعاملات:
            windows : dict من create_windows()

        المخرجات:
            (train_windows, val_windows, test_windows)
        """
        n = len(windows["land_ids"])
        if n == 0:
            return (
                {k: np.array([]) for k in windows if k != "static_categorical"},
                {k: np.array([]) for k in windows if k != "static_categorical"},
                {k: np.array([]) for k in windows if k != "static_categorical"},
            )

        train_end = int(n * self.train_ratio)
        val_end = int(n * (self.train_ratio + self.val_ratio))

        splits = []
        for start, end in [(0, train_end), (train_end, val_end), (val_end, n)]:
            split = {}
            for key, val in windows.items():
                if key == "land_ids":
                    split[key] = val[start:end]
                elif key == "static_categorical":
                    split[key] = {k: v[start:end] for k, v in val.items()}
                elif isinstance(val, np.ndarray) and val.size > 0:
                    split[key] = val[start:end]
                else:
                    split[key] = val
            splits.append(split)

        logger.info(
            f"تقسيم زمني: تدريب={train_end}, تحقق={val_end - train_end}, "
            f"اختبار={n - val_end}"
        )

        return splits[0], splits[1], splits[2]

    # ────────────────────────────────────────────
    # 1.7 الدالة الشاملة للتحضير
    # ────────────────────────────────────────────

    def prepare_for_tft(
        self,
        df: "pd.DataFrame",
        handle_missing: bool = True,
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict[str, np.ndarray]]:
        """
        خط أنابيب التحضير الشامل: تنظيف → ميزات → تطبيع → نوافذ → تقسيم.

        المعاملات:
            df             : DataFrame خام بالتاريخ والأسعار
            handle_missing : معالجة القيم المفقودة تلقائياً

        المخرجات:
            (train_windows, val_windows, test_windows)
        """
        pd  # confirm pandas is available

        if handle_missing:
            df = self.handle_missing_values(df)

        # استخراج الميزات الزمنية
        df = self.extract_time_features(df)

        # الترتيب الزمني
        df = df.sort_values([self.date_col, "land_id"]).reset_index(drop=True)

        # حساب التطبيع
        self.fit_scalers(df)

        # تطبيق التطبيع
        df = self.apply_scaling(df)

        # إنشاء النوافذ
        windows = self.create_windows(df)

        # التقسيم الزمني
        train, val, test = self.temporal_train_val_test_split(windows)

        return train, val, test

    def get_scalers_state(self) -> Dict[str, Any]:
        """حفظ حالة أدوات التطبيع كقاموس."""
        return {
            "scalers": self.scalers,
            "target_mean": self.target_mean,
            "target_std": self.target_std,
            "observed_columns": self.observed_columns,
            "known_future_columns": self.known_future_columns,
            "static_columns": self.static_columns,
            "encoder_length": self.encoder_length,
            "decoder_length": self.decoder_length,
            "target_col": self.target_col,
            "date_col": self.date_col,
        }

    def load_scalers_state(self, state: Dict[str, Any]):
        """استعادة حالة أدوات التطبيع."""
        self.scalers = state["scalers"]
        self.target_mean = state["target_mean"]
        self.target_std = state["target_std"]
        self.observed_columns = state["observed_columns"]
        self.known_future_columns = state["known_future_columns"]
        self.static_columns = state["static_columns"]
        self.encoder_length = state["encoder_length"]
        self.decoder_length = state["decoder_length"]
        self.target_col = state.get("target_col", self.target_col)
        self.date_col = state.get("date_col", self.date_col)


# ════════════════════════════════════════════════════════════════
# 2. مجموعة بيانات PyTorch
# ════════════════════════════════════════════════════════════════

class LandTimeSeriesDataset(torch.utils.data.Dataset):
    """
    مجموعة بيانات PyTorch لنوافذ السلاسل الزمنية للأراضي.
    ────────────────────────────────────────────────────────────
    تُحوّل مخرجات TimeSeriesPreprocessor.create_windows()
    إلى تنسيق متوافق مع PyTorch DataLoader.
    """

    def __init__(self, windows: Dict[str, np.ndarray]):
        pass  # torch already imported at module level

        self.observed_encoder = torch.from_numpy(
            windows["observed_encoder"]
        ).float() if windows["observed_encoder"].size > 0 else torch.zeros(1, 1, 1)

        self.known_future_encoder = torch.from_numpy(
            windows["known_future_encoder"]
        ).float() if windows["known_future_encoder"].size > 0 else torch.zeros(1, 1, 1)

        self.observed_decoder = torch.from_numpy(
            windows["observed_decoder"]
        ).float() if windows["observed_decoder"].size > 0 else torch.zeros(1, 1, 1)

        self.known_future_decoder = torch.from_numpy(
            windows["known_future_decoder"]
        ).float() if windows["known_future_decoder"].size > 0 else torch.zeros(1, 1, 1)

        self.targets = torch.from_numpy(
            windows["targets"]
        ).float() if windows["targets"].size > 0 else torch.zeros(1, 1, 1)

        # المتغيرات الثابتة
        self.static_continuous = torch.from_numpy(
            windows["static_continuous"]
        ).float() if windows["static_continuous"].size > 0 else torch.zeros(1, 1)

        self.static_categorical = {}
        if "static_categorical" in windows:
            for name, arr in windows["static_categorical"].items():
                if isinstance(arr, np.ndarray) and arr.size > 0:
                    self.static_categorical[name] = torch.from_numpy(arr).long()
                else:
                    self.static_categorical[name] = torch.zeros(1, dtype=torch.long)

        self.land_ids = windows.get("land_ids", [])

    def __len__(self) -> int:
        return self.observed_encoder.size(0)

    def __getitem__(self, idx: int) -> Dict[str, "torch.Tensor"]:
        return {
            "observed_encoder": self.observed_encoder[idx],
            "known_future_encoder": self.known_future_encoder[idx],
            "observed_decoder": self.observed_decoder[idx],
            "known_future_decoder": self.known_future_decoder[idx],
            "targets": self.targets[idx],
            "static_continuous": self.static_continuous[idx] if idx < len(self.static_continuous) else torch.zeros(1),
            "static_categorical": {
                k: v[idx] if idx < len(v) else torch.tensor(0, dtype=torch.long)
                for k, v in self.static_categorical.items()
            },
        }


def create_dataloaders(
    train_windows: Dict[str, np.ndarray],
    val_windows: Optional[Dict[str, np.ndarray]] = None,
    test_windows: Optional[Dict[str, np.ndarray]] = None,
    batch_size: int = 32,
    num_workers: int = 0,
) -> Dict[str, Any]:
    """
    إنشاء DataLoaders للتدريب والتحقق والاختبار.

    المعاملات:
        train_windows : نوافذ التدريب
        val_windows   : نوافذ التحقق (اختياري)
        test_windows  : نوافذ الاختبار (اختياري)
        batch_size    : حجم الدفعة
        num_workers   : عدد عمال التحميل

    المخرجات:
        dict {"train": DataLoader, "val": DataLoader, "test": DataLoader}
    """
    pass  # torch already imported at module level

    loaders = {}
    for name, windows in [
        ("train", train_windows),
        ("val", val_windows),
        ("test", test_windows),
    ]:
        if windows is not None and (
            isinstance(windows.get("land_ids", []), list)
            and len(windows.get("land_ids", [])) > 0
        ):
            dataset = LandTimeSeriesDataset(windows)
            shuffle = (name == "train")
            loaders[name] = torch.utils.data.DataLoader(
                dataset,
                batch_size=batch_size,
                shuffle=shuffle,
                num_workers=num_workers,
                pin_memory=True if torch.cuda.is_available() else False,
            )

    logger.info(
        f"تم إنشاء DataLoaders: "
        + ", ".join(f"{k}={len(v.dataset)} عينة" for k, v in loaders.items())
    )

    return loaders


# ════════════════════════════════════════════════════════════════
# 3. دالة التدريب الرئيسية
# ════════════════════════════════════════════════════════════════

def train_tft_model(
    X_train: Union[np.ndarray, Dict[str, np.ndarray]],
    y_train: Optional[np.ndarray] = None,
    X_val: Optional[Union[np.ndarray, Dict[str, np.ndarray]]] = None,
    y_val: Optional[np.ndarray] = None,
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-5,
    hidden_size: int = 64,
    dropout: float = 0.2,
    num_heads: int = 4,
    encoder_length: int = 24,
    decoder_length: int = 12,
    early_stopping_patience: int = 7,
    reduce_lr_patience: int = 3,
    reduce_lr_factor: float = 0.5,
    model_save_path: Optional[str] = None,
    device: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    تدريب نموذج TFT على بيانات أسعار الأراضي.

    هذه هي الدالة الرئيسية للتدريب — تتعامل مع:
      - إنشاء النموذج (إن لم يُمرّر)
      - تحسين المعاملات بـ AdamW
      - التعلم المجدول (ReduceLROnPlateau)
      - التوقف المبكر (Early Stopping)
      - تسجيل المقاييس
      - حفظ أفضل نموذج

    المعاملات:
        X_train  : (num_samples, encoder_length, input_dim) بيانات التدريب
        y_train  : (num_samples, decoder_length) أهداف التدريب
        X_val    : بيانات التحقق (اختياري)
        y_val    : أهداف التحقق (اختياري)
        epochs   : عدد الحقب (افتراضي: 50)
        batch_size : حجم الدفعة (افتراضي: 32)
        learning_rate : معدل التعلم (افتراضي: 1e-3)
        weight_decay  : تنظيم L2 (افتراضي: 1e-5)
        hidden_size   : حجم الطبقة المخفية (افتراضي: 64)
        dropout       : معدل الإسقاط (افتراضي: 0.2)
        num_heads     : عدد رؤوس الانتباه (افتراضي: 4)
        encoder_length : طول نافذة الإدخال (افتراضي: 24)
        decoder_length : طول نافذة التنبؤ (افتراضي: 12)
        early_stopping_patience : صبر التوقف المبكر (افتراضي: 7)
        reduce_lr_patience : صبر تقليل معدل التعلم (افتراضي: 3)
        reduce_lr_factor  : عامل تقليل معدل التعلم (افتراضي: 0.5)
        model_save_path   : مسار حفظ النموذج (افتراضي: تلقائي)
        device    : الجهاز (auto/cpu/cuda)
        verbose   : طباعة التقدم

    المخرجات:
        dict {
            "model": TemporalFusionTransformer,
            "training_history": dict {epoch, train_loss, val_loss, lr, epoch_time},
            "best_val_loss": float,
            "best_epoch": int,
            "model_save_path": str,
            "metrics": dict {mae, rmse, mape, ...},
        }

    مثال:
        >>> from core.ai.tft.training import train_tft_model
        >>> import numpy as np
        >>> X = np.random.randn(100, 24, 5).astype(np.float32)
        >>> y = np.random.randn(100, 12).astype(np.float32)
        >>> result = train_tft_model(X, y, epochs=10)
    """
    pass  # torch already imported at module level

    from core.ai.tft.model import create_tft_model, QuantileLoss, get_model_info

    # ── إعداد الجهاز ──
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)

    if verbose:
        logger.info(f"الجهاز: {device}")

    # ── إعداد مسار الحفظ ──
    if model_save_path is None:
        model_save_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models",
            "tft_land_price_model.pt",
        )
    os.makedirs(os.path.dirname(model_save_path), exist_ok=True)

    # ── تحضير البيانات ──
    # دعم X_train كـ numpy array مباشرة أو كـ dict من النوافذ
    if isinstance(X_train, dict):
        # البيانات جاهزة من TimeSeriesPreprocessor
        preprocessor = TimeSeriesPreprocessor(
            encoder_length=encoder_length,
            decoder_length=decoder_length,
        )
        dataloaders = create_dataloaders(
            X_train, X_val, batch_size=batch_size
        )
        train_loader = dataloaders["train"]
        val_loader = dataloaders.get("val")

        # حساب أبعاد المدخل من البيانات
        input_dim = X_train["observed_encoder"].shape[2] + X_train["known_future_encoder"].shape[2]
        output_dim = 1
        observed_dim = X_train["observed_encoder"].shape[2]
        known_future_dim = X_train["known_future_encoder"].shape[2]
        static_continuous_dim = X_train["static_continuous"].shape[1] if X_train["static_continuous"].ndim > 1 else 0
    else:
        # X_train/y_train كـ numpy arrays
        n_samples = len(X_train)
        if X_train.ndim == 2:
            X_train = X_train.reshape(n_samples, encoder_length, -1)

        input_dim = X_train.shape[2] if X_train.ndim == 3 else 1
        output_dim = 1
        observed_dim = max(1, input_dim // 2)
        known_future_dim = max(1, input_dim - observed_dim)
        static_continuous_dim = 4

        # إنشاء DataLoaders مباشرة من numpy
        train_dataset = torch.utils.data.TensorDataset(
            torch.from_numpy(X_train).float(),
            torch.from_numpy(y_train.reshape(n_samples, -1, 1)).float(),
        )
        train_loader = torch.utils.data.DataLoader(
            train_dataset, batch_size=batch_size, shuffle=True
        )

        val_loader = None
        if X_val is not None and y_val is not None:
            n_val = len(X_val)
            if X_val.ndim == 2:
                X_val = X_val.reshape(n_val, encoder_length, -1)
            val_dataset = torch.utils.data.TensorDataset(
                torch.from_numpy(X_val).float(),
                torch.from_numpy(y_val.reshape(n_val, -1, 1)).float(),
            )
            val_loader = torch.utils.data.DataLoader(
                val_dataset, batch_size=batch_size, shuffle=False
            )

    # ── إنشاء النموذج ──
    model = create_tft_model(
        input_dim=input_dim,
        output_dim=output_dim,
        hidden_size=hidden_size,
        dropout=dropout,
        num_heads=num_heads,
        encoder_length=encoder_length,
        decoder_length=decoder_length,
        observed_dim=observed_dim,
        known_future_dim=known_future_dim,
        static_continuous_dim=static_continuous_dim,
    ).to(device)

    if verbose:
        info = get_model_info(model)
        logger.info(
            f"نموذج TFT: {info['total_parameters']:,} معامل, "
            f"الحجم: {info['model_size_mb']} MB"
        )

    # ── دالة الخسارة والمُحسِّن ──
    quantiles = model.quantiles
    criterion = QuantileLoss(quantiles).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )

    # جدولة معدل التعلم
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=reduce_lr_factor,
        patience=reduce_lr_patience, min_lr=1e-6,
    )

    # ── التدريب ──
    training_history = {
        "train_loss": [],
        "val_loss": [],
        "lr": [],
        "epoch_time": [],
    }

    best_val_loss = float("inf")
    best_epoch = 0
    best_state_dict = None
    patience_counter = 0

    if verbose:
        logger.info(
            f"بدء التدريب: {epochs} حقبة, batch_size={batch_size}, "
            f"lr={learning_rate}, device={device}"
        )

    for epoch in range(1, epochs + 1):
        epoch_start = time.time()

        # ── مرحلة التدريب ──
        model.train()
        train_losses = []

        for batch in train_loader:
            optimizer.zero_grad()

            if isinstance(batch, dict):
                # بيانات من TimeSeriesPreprocessor
                obs_enc = batch["observed_encoder"].to(device)
                known_enc = batch["known_future_encoder"].to(device)
                obs_dec = batch["observed_decoder"].to(device)
                known_dec = batch["known_future_decoder"].to(device)
                targets = batch["targets"].to(device)
                static_cat = batch.get("static_categorical")
                static_cont = batch.get("static_continuous")
                if static_cont is not None:
                    static_cont = static_cont.to(device)
            else:
                # بيانات numpy مباشرة
                x_batch, y_batch = batch
                x_batch = x_batch.to(device)
                y_batch = y_batch.to(device)
                half = x_batch.shape[-1] // 2
                obs_enc = x_batch[:, :, :half]
                known_enc = x_batch[:, :, half:]
                obs_dec = torch.zeros_like(obs_enc[:, :decoder_length, :])
                known_dec = known_enc[:, -decoder_length:, :]
                if known_dec.shape[1] < decoder_length:
                    known_dec = torch.nn.functional.pad(
                        known_dec, (0, 0, decoder_length - known_dec.shape[1], 0)
                    )
                targets = y_batch
                static_cat = None
                static_cont = None

            # التمرير الأمامي
            outputs = model(
                observed_encoder=obs_enc,
                known_future_encoder=known_enc,
                observed_decoder=obs_dec,
                known_future_decoder=known_dec,
                static_categorical=static_cat,
                static_continuous=static_cont,
            )

            loss = criterion(outputs["predictions"], targets)
            loss.backward()

            # قص التدرجات لمنع الانفجار
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            train_losses.append(loss.item())

        avg_train_loss = np.mean(train_losses) if train_losses else 0.0

        # ── مرحلة التحقق ──
        avg_val_loss = 0.0
        if val_loader is not None:
            model.eval()
            val_losses = []
            with torch.no_grad():
                for batch in val_loader:
                    if isinstance(batch, dict):
                        obs_enc = batch["observed_encoder"].to(device)
                        known_enc = batch["known_future_encoder"].to(device)
                        obs_dec = batch["observed_decoder"].to(device)
                        known_dec = batch["known_future_decoder"].to(device)
                        targets = batch["targets"].to(device)
                        static_cat = batch.get("static_categorical")
                        static_cont = batch.get("static_continuous")
                        if static_cont is not None:
                            static_cont = static_cont.to(device)
                    else:
                        x_batch, y_batch = batch
                        x_batch = x_batch.to(device)
                        y_batch = y_batch.to(device)
                        half = x_batch.shape[-1] // 2
                        obs_enc = x_batch[:, :, :half]
                        known_enc = x_batch[:, :, half:]
                        obs_dec = torch.zeros_like(obs_enc[:, :decoder_length, :])
                        known_dec = known_enc[:, -decoder_length:, :]
                        if known_dec.shape[1] < decoder_length:
                            known_dec = torch.nn.functional.pad(
                                known_dec, (0, 0, decoder_length - known_dec.shape[1], 0)
                            )
                        targets = y_batch
                        static_cat = None
                        static_cont = None

                    outputs = model(
                        observed_encoder=obs_enc,
                        known_future_encoder=known_enc,
                        observed_decoder=obs_dec,
                        known_future_decoder=known_dec,
                        static_categorical=static_cat,
                        static_continuous=static_cont,
                    )
                    loss = criterion(outputs["predictions"], targets)
                    val_losses.append(loss.item())

            avg_val_loss = np.mean(val_losses) if val_losses else 0.0
            scheduler.step(avg_val_loss)

        # ── التسجيل ──
        epoch_time = time.time() - epoch_start
        current_lr = optimizer.param_groups[0]["lr"]

        training_history["train_loss"].append(avg_train_loss)
        training_history["val_loss"].append(avg_val_loss)
        training_history["lr"].append(current_lr)
        training_history["epoch_time"].append(epoch_time)

        if verbose and (epoch % 5 == 0 or epoch == 1):
            val_str = f", val_loss={avg_val_loss:.6f}" if val_loader else ""
            logger.info(
                f"  حقبة {epoch:3d}/{epochs}: "
                f"train_loss={avg_train_loss:.6f}{val_str}, "
                f"lr={current_lr:.2e}, وقت={epoch_time:.1f}s"
            )

        # ── حفظ أفضل نموذج ──
        if val_loader is not None:
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                best_epoch = epoch
                best_state_dict = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                patience_counter = 0

                # حفظ النموذج على القرص
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": best_state_dict,
                    "optimizer_state_dict": optimizer.state_dict(),
                    "best_val_loss": best_val_loss,
                    "model_config": {
                        "input_dim": input_dim,
                        "output_dim": output_dim,
                        "hidden_size": hidden_size,
                        "num_heads": num_heads,
                        "encoder_length": encoder_length,
                        "decoder_length": decoder_length,
                        "observed_dim": observed_dim,
                        "known_future_dim": known_future_dim,
                        "static_continuous_dim": static_continuous_dim,
                        "quantiles": quantiles,
                    },
                    "training_history": training_history,
                }, model_save_path)

                if verbose:
                    logger.info(f"  ★ أفضل نموذج محفوظ: val_loss={best_val_loss:.6f}")
            else:
                patience_counter += 1

            # التوقف المبكر
            if patience_counter >= early_stopping_patience:
                if verbose:
                    logger.info(
                        f"  ⛔ التوقف المبكر بعد {epoch} حقبة "
                        f"(لا تحسّن منذ {early_stopping_patience} حقب)"
                    )
                break
        else:
            # بدون تحقق — حفظ آخر نموذج
            if epoch == epochs:
                best_state_dict = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                best_val_loss = avg_train_loss
                best_epoch = epoch

    # ── استعادة أفضل نموذج ──
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)
        model.to(device)

    # ── حساب مقاييس التقييم ──
    metrics = {
        "best_val_loss": best_val_loss,
        "best_epoch": best_epoch,
        "total_epochs": epoch,
        "total_training_time": sum(training_history["epoch_time"]),
    }

    if verbose:
        logger.info(
            f"\nاكتمل التدريب:\n"
            f"  أفضل حقبة: {best_epoch}\n"
            f"  أفضل خسارة تحقق: {best_val_loss:.6f}\n"
            f"  إجمالي الوقت: {metrics['total_training_time']:.1f}s\n"
            f"  مسار الحفظ: {model_save_path}"
        )

    return {
        "model": model,
        "training_history": training_history,
        "best_val_loss": best_val_loss,
        "best_epoch": best_epoch,
        "model_save_path": model_save_path,
        "metrics": metrics,
    }


# ════════════════════════════════════════════════════════════════
# 4. التقييم والتنبؤ
# ════════════════════════════════════════════════════════════════

def evaluate_model(
    model: Any,
    test_windows: Dict[str, np.ndarray],
    preprocessor: Optional[TimeSeriesPreprocessor] = None,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """
    تقييم نموذج TFT على بيانات الاختبار.

    يحسب:
        - MAE (Mean Absolute Error)
        - RMSE (Root Mean Squared Error)
        - MAPE (Mean Absolute Percentage Error)
        - P50 vs Actual comparison

    المعاملات:
        model       : نموذج TFT مُدرَّب
        test_windows : نوافذ الاختبار
        preprocessor : معالج البيانات (لعكس التطبيع)
        device      : الجهاز

    المخرجات:
        dict بالمقاييس والتنبؤات
    """
    pass  # torch already imported at module level

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)

    model.eval()
    model.to(device)

    dataset = LandTimeSeriesDataset(test_windows)
    loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=False)

    all_predictions = []
    all_targets = []

    with torch.no_grad():
        for batch in loader:
            obs_enc = batch["observed_encoder"].to(device)
            known_enc = batch["known_future_encoder"].to(device)
            obs_dec = batch["observed_decoder"].to(device)
            known_dec = batch["known_future_decoder"].to(device)
            targets = batch["targets"].to(device)

            static_cat = batch.get("static_categorical")
            static_cont = batch.get("static_continuous")
            if static_cat is not None:
                static_cat = {k: v.to(device) for k, v in static_cat.items()}
            if static_cont is not None:
                static_cont = static_cont.to(device)

            outputs = model(
                observed_encoder=obs_enc,
                known_future_encoder=known_enc,
                observed_decoder=obs_dec,
                known_future_decoder=known_dec,
                static_categorical=static_cat,
                static_continuous=static_cont,
            )

            # P50 (الوسيط)
            p50_pred = outputs["predictions"][:, :, 1, :]  # (batch, seq, 1)
            all_predictions.append(p50_pred.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    predictions = np.concatenate(all_predictions, axis=0)
    targets = np.concatenate(all_targets, axis=0)

    # عكس التطبيع إذا توفر المعالج
    if preprocessor is not None:
        predictions = preprocessor.inverse_transform_target(predictions)
        targets = preprocessor.inverse_transform_target(targets)

    # حساب المقاييس
    errors = predictions - targets
    mae = np.mean(np.abs(errors))
    rmse = np.sqrt(np.mean(errors ** 2))
    mape = np.mean(np.abs(errors / (targets + 1e-8))) * 100

    metrics = {
        "mae": round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "mape_pct": round(float(mape), 2),
        "num_samples": len(predictions),
        "mean_actual": round(float(np.mean(targets)), 2),
        "mean_predicted": round(float(np.mean(predictions)), 2),
        "predictions_shape": list(predictions.shape),
    }

    logger.info(
        f"تقييم النموذج:\n"
        f"  MAE:  {metrics['mae']:,.2f}\n"
        f"  RMSE: {metrics['rmse']:,.2f}\n"
        f"  MAPE: {metrics['mape_pct']:.1f}%\n"
        f"  العينات: {metrics['num_samples']}"
    )

    return {
        "metrics": metrics,
        "predictions": predictions,
        "targets": targets,
    }


# ════════════════════════════════════════════════════════════════
# 5. حفظ وتحميل النموذج
# ════════════════════════════════════════════════════════════════

def save_model(
    model: Any,
    preprocessor: TimeSeriesPreprocessor,
    path: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    حفظ النموذج والمعالج معاً.

    يحفظ:
        - أوزان النموذج
        - حالة المعالج (scalers, means, stds)
        - بيانات وصفية (metadata)
    """
    pass  # torch already imported at module level

    os.makedirs(os.path.dirname(path), exist_ok=True)

    save_dict = {
        "model_state_dict": model.state_dict(),
        "preprocessor_state": preprocessor.get_scalers_state(),
        "model_config": {
            "input_dim": model.input_dim,
            "output_dim": model.output_dim,
            "hidden_size": model.hidden_size,
            "num_heads": model.num_heads,
            "encoder_length": model.encoder_length,
            "decoder_length": model.decoder_length,
            "quantiles": model.quantiles,
            "dropout": model.dropout_rate,
            "observed_dim": model.observed_dim,
            "known_future_dim": model.known_future_dim,
            "static_continuous_dim": model.static_continuous_dim,
            "lstm_layers": model.lstm_layers,
        },
        "metadata": metadata or {},
        "saved_at": datetime.now().isoformat(),
        "version": "1.0.0",
    }

    torch.save(save_dict, path)
    logger.info(f"تم حفظ النموذج في: {path}")


def load_model(
    path: str,
    device: Optional[str] = None,
) -> Tuple[Any, TimeSeriesPreprocessor]:
    """
    تحميل نموذج محفوظ مع المعالج.

    المعاملات:
        path   : مسار الملف المحفوظ
        device : الجهاز (auto/cpu/cuda)

    المخرجات:
        (model, preprocessor)
    """
    from core.ai.tft.model import create_tft_model

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)

    checkpoint = torch.load(path, map_location=device, weights_only=False)

    config = checkpoint["model_config"]
    model = create_tft_model(
        input_dim=config["input_dim"],
        output_dim=config["output_dim"],
        hidden_size=config["hidden_size"],
        num_heads=config["num_heads"],
        encoder_length=config["encoder_length"],
        decoder_length=config["decoder_length"],
        quantiles=config.get("quantiles"),
        dropout=config.get("dropout", 0.2),
        observed_dim=config.get("observed_dim", 1),
        known_future_dim=config.get("known_future_dim", 2),
        static_continuous_dim=config.get("static_continuous_dim", 4),
        lstm_layers=config.get("lstm_layers", 2),
    )

    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    # استعادة المعالج
    preprocessor = TimeSeriesPreprocessor(
        encoder_length=config["encoder_length"],
        decoder_length=config["decoder_length"],
    )
    if "preprocessor_state" in checkpoint:
        preprocessor.load_scalers_state(checkpoint["preprocessor_state"])

    logger.info(
        f"تم تحميل النموذج من: {path} "
        f"(حُفظ في: {checkpoint.get('saved_at', 'غير معروف')})"
    )

    return model, preprocessor


# ════════════════════════════════════════════════════════════════
# 6. التنبؤ السريع (API Endpoint Helper)
# ════════════════════════════════════════════════════════════════

def predict_future_prices(
    model: Any,
    preprocessor: TimeSeriesPreprocessor,
    recent_data: "pd.DataFrame",
    future_months: int = 12,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """
    تنبؤ بأسعار الأراضي للأشهر القادمة.

    هذه الدالة مُصممة للاستخدام في نقاط النهاية API.

    المعاملات:
        model         : نموذج TFT مُدرَّب
        preprocessor  : معالج البيانات
        recent_data   : DataFrame بآخر encoder_length شهراً من البيانات
        future_months : عدد أشهر التنبؤ
        device        : الجهاز

    المخرجات:
        dict {
            "predicted_prices": list[float] — الأسعار المتوقعة (P50)
            "lower_bound": list[float] — حد الثقة الأدنى (P10)
            "upper_bound": list[float] — حد الثقة الأعلى (P90)
            "months": list[str] — أسماء الأشهر
        }
    """
    pass  # torch already imported at module level

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)

    model.eval()

    # معالجة البيانات الحديثة
    recent_data = preprocessor.handle_missing_values(recent_data)
    recent_data = preprocessor.extract_time_features(recent_data)
    recent_data = preprocessor.apply_scaling(recent_data)
    recent_data = recent_data.sort_values(preprocessor.date_col).tail(
        preprocessor.encoder_length
    )

    # استخراج المدخلات
    observed_cols = preprocessor.observed_columns or ["السعر_للمتر"]
    known_cols = preprocessor.known_future_columns or ["شهر", "الموسم"]

    obs_data = recent_data[observed_cols].values
    known_data = recent_data[known_cols].values

    # إنشاء مدخلات المستقبل (أصفار للمُلاحظة، ميزات زمنية معروفة)
    last_date = recent_data[preprocessor.date_col].max()
    future_dates = [
        last_date + pd.DateOffset(months=i + 1) for i in range(future_months)
    ]

    future_known = []
    for date in future_dates:
        month = date.month
        quarter = (month - 1) // 3 + 1
        season = {1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 0}[month]
        is_year_end = float(month in [6, 7, 8])
        day_of_year = date.timetuple().tm_yday

        row = []
        for col in known_cols:
            if col == "شهر":
                row.append(month)
            elif col == "ربع_سنة":
                row.append(quarter)
            elif col == "الموسم":
                row.append(season)
            elif col == "هل_نهاية_السنة":
                row.append(is_year_end)
            elif col == "يوم_من_بداية_السنة":
                row.append(day_of_year)
            else:
                row.append(0.0)
        future_known.append(row)

    future_known = np.array(future_known, dtype=np.float32)

    # تحويل إلى tensors
    obs_enc = torch.from_numpy(obs_data).unsqueeze(0).float().to(device)
    known_enc = torch.from_numpy(known_data).unsqueeze(0).float().to(device)
    obs_dec = torch.zeros(1, future_months, obs_data.shape[1], device=device)
    known_dec = torch.from_numpy(future_known).unsqueeze(0).float().to(device)

    # المتغيرات الثابتة
    static_cont = torch.zeros(1, 4, device=device)

    # التنبؤ
    with torch.no_grad():
        outputs = model(
            observed_encoder=obs_enc,
            known_future_encoder=known_enc,
            observed_decoder=obs_dec,
            known_future_decoder=known_dec,
            static_continuous=static_cont,
        )

    preds = outputs["predictions"].squeeze(0).cpu().numpy()  # (seq, num_q, 1)

    # عكس التطبيع
    p10 = preprocessor.inverse_transform_target(preds[:, 0, :].flatten())
    p50 = preprocessor.inverse_transform_target(preds[:, 1, :].flatten())
    p90 = preprocessor.inverse_transform_target(preds[:, 2, :].flatten())

    month_names = [d.strftime("%Y-%m") for d in future_dates]

    return {
        "predicted_prices": [round(float(p), 2) for p in p50],
        "lower_bound": [round(float(p), 2) for p in p10],
        "upper_bound": [round(float(p), 2) for p in p90],
        "months": month_names,
        "quantiles": model.quantiles,
    }