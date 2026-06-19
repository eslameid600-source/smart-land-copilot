"""
مُسجِّل التعلم الآلي — المطابقة التكيفية v1.0
=================================================
Smart Land Management Copilot — ML-Enhanced Match Scorer
=========================================================
نظام مطابقة هجين يجمع بين:
  • 60% نموذج تعلم آلي (GradientBoosting) — يتكيف مع سلوك المستثمرين الحقيقيين
  • 40% قواعد تقييم مرجّحة — ضمانات حدّية (تطابق النشاط، المرافق، إلخ)

التركيب:  pip install scikit-learn joblib
التشغيل:  python -c "from core.matchmaking.ml_scorer import MLScoreEngine; print(MLScoreEngine())"
"""

from __future__ import annotations

import logging
import os
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.domain.land_database import (
    get_all_lands,
    ALL_UTILITIES,
    compute_land_quality_rating,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# ثوابت التهيئة
# ──────────────────────────────────────────────────────────────

# مسار حفظ النموذج المدرب (بجانب هذا الملف)
_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ml_models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "match_scorer.joblib")
_FEATURE_NAMES_PATH = os.path.join(_MODEL_DIR, "feature_names.json")

# نسب الدمج الهجين
ML_WEIGHT = 0.60       # وزن النموذج
RULE_WEIGHT = 0.40     # وزن القواعد

# ترتيب الجودة الرقمي (للتشفير)
_QUALITY_NUMERIC = {"AAA": 4.0, "AA": 3.0, "A": 2.0, "B": 1.0}

# أنشطة الأراضي المتاحة
_ACTIVITY_TYPES = ["صناعي", "زراعي", "لوجستي", "سكني", "تجاري"]

# المحافظات المتاحة
_GOVERNORATES = [
    "القاهرة", "الشرقية", "الإسكندرية", "السويس", "دمياط",
    "بورسعيد", "الغربية", "المنوفية", "البحر الأحمر", "الجيزة",
    "قنا", "أسيوط", "الإسماعيلية", "الفيوم",
]

# اتجاهات السوق
_MARKET_DIRECTIONS = {
    "مرتفع بسرعة": 1.0, "مرتفع": 0.8, "مستقر": 0.5,
    "منخفض": 0.3, "منخفض بسرعة": 0.1,
}

# مستويات المخاطر الزلزالية
_SEISMIC_RISK = {"منخفضة": 1.0, "متوسطة": 0.5, "عالية": 0.2}


# ──────────────────────────────────────────────────────────────
# استخراج الميزات (Feature Engineering)
# ──────────────────────────────────────────────────────────────

def _count_utilities_from_str(utilities_str: str) -> int:
    """حساب عدد المرافق المتاحة من أصل 4."""
    if not utilities_str:
        return 0
    return sum(1 for u in ALL_UTILITIES if u in utilities_str)


def extract_features(
    land: Dict,
    criteria_activity: Optional[str] = None,
    criteria_max_price: Optional[float] = None,
    criteria_min_area: Optional[float] = None,
    criteria_utilities: Optional[List[str]] = None,
    criteria_governorate: Optional[str] = None,
    criteria_min_quality: Optional[str] = None,
    criteria_auction_pref: bool = False,
    criteria_budget: Optional[float] = None,
) -> np.ndarray:
    """
    تحويل خصائص الأرض ومعايير المستثمر إلى متجه ميزات رقمي.

    المتجه يحتوي على 18 ميزة:
      ── ميزات الأرض (10) ──
        0. log(المساحة)
        1. log(السعر/م²)
        2. log(السعر الإجمالي)
        3. عدد المرافق / 4
        4. تصنيف الجودة (1-4)
        5. المسافة للطريق السريع (معكوس_log)
        6. المسافة للميناء (معكوس_log)
        7. قدرة الكهرباء (normalized)
        8. اتجاه السوق (0-1)
        9. هل مزاد (0/1)

      ── ميزات التفاعل (8) ──
        10. تطابق النشاط (0/1)
        11. نسبة المساحة الفعلية/المطلوبة
        12. نسبة السعر المطلوب/الفعلي
        13. نسبة تغطية المرافق
        14. تطابق المحافظة (0/1)
        15. فجوة الجودة (الطلب - الفعلي)
        16. تفضيل المزاد ∩ مزاد فعلي (0/1)
        17. ملاءمة الميزانية الإجمالية
    """
    feat = np.zeros(18, dtype=np.float64)

    # ── ميزات الأرض ──
    area = float(land.get("المساحة_متر_مربع", 1))
    price_sqm = float(land.get("السعر_للمتر_المربع", 1))
    total_price = area * price_sqm

    feat[0] = math.log1p(area) / math.log1p(1_000_000)       # log المساحة (معيَّر)
    feat[1] = math.log1p(price_sqm) / math.log1p(20_000)      # log السعر/م²
    feat[2] = math.log1p(total_price) / math.log1p(5_000_000_000)  # log السعر الكلي

    util_count = _count_utilities_from_str(land.get("المرافق_المتاحة", ""))
    feat[3] = util_count / 4.0

    quality = land.get("تصنيف_الجودة", "B")
    feat[4] = _QUALITY_NUMERIC.get(quality, 1.0) / 4.0

    hw_km = float(land.get("المسافة_لأقرب_طريق_سريع_كم", 50))
    feat[5] = 1.0 / (1.0 + math.log1p(hw_km))               # معكوس_log القرب

    port_km = float(land.get("المسافة_لأقرب_ميناء_كم", 200))
    feat[6] = 1.0 / (1.0 + math.log1p(port_km))

    elec = float(land.get("قدرة_الكهرباء_ميجاواط", 0))
    feat[7] = min(elec / 100.0, 1.0)                         # معيَّر حتى 100 ميجاواط

    market_dir = land.get("اتجاه_السوق", "مستقر")
    feat[8] = _MARKET_DIRECTIONS.get(market_dir, 0.5)

    feat[9] = 1.0 if land.get("حالة_الاستثمار") == "مزاد علني حكومي" else 0.0

    # ── ميزات التفاعل ──
    # 10. تطابق النشاط
    if criteria_activity:
        feat[10] = 1.0 if land.get("نوع_النشاط") == criteria_activity else 0.0

    # 11. نسبة المساحة
    if criteria_min_area and criteria_min_area > 0:
        feat[11] = min(area / criteria_min_area, 2.0) / 2.0
    else:
        feat[11] = 1.0

    # 12. نسبة السعر
    if criteria_max_price and criteria_max_price > 0:
        feat[12] = min(criteria_max_price / price_sqm, 1.0)
    else:
        feat[12] = 1.0

    # 13. تغطية المرافق
    if criteria_utilities:
        matched = sum(1 for u in criteria_utilities if u in land.get("المرافق_المتاحة", ""))
        feat[13] = matched / len(criteria_utilities) if criteria_utilities else 1.0
    else:
        feat[13] = 1.0

    # 14. تطابق المحافظة
    if criteria_governorate:
        feat[14] = 1.0 if land.get("المحافظة") == criteria_governorate else 0.0

    # 15. فجوة الجودة (موجب = الأرض أفضل من المطلوب)
    if criteria_min_quality:
        requested = _QUALITY_NUMERIC.get(criteria_min_quality, 1.0)
        actual = _QUALITY_NUMERIC.get(quality, 1.0)
        feat[15] = (actual - requested) / 3.0   # -1 إلى +1
    else:
        feat[15] = 0.0

    # 16. تفضيل المزاد ∩ مزاد فعلي
    if criteria_auction_pref:
        feat[16] = 1.0 if feat[9] == 1.0 else 0.0
    else:
        feat[16] = 0.0

    # 17. ملاءمة الميزانية الإجمالية
    if criteria_budget and criteria_budget > 0:
        feat[17] = min(criteria_budget / total_price, 1.5) / 1.5
    else:
        feat[17] = 1.0

    return feat


# ──────────────────────────────────────────────────────────────
# توليد بيانات التدريب التجريبية
# ──────────────────────────────────────────────────────────────

def generate_training_data(
    n_samples: int = 5000,
    seed: int = 42,
) -> pd.DataFrame:
    """
    توليد بيانات تدريب تجريبية من قاعدة بيانات الأراضي.

    كل صف يمثل تفاعل مستثمر محتمل مع أرض:
      - خصائص الأرض (من land_database الحقيقية)
      - معايير المستثمر (عشوائية واقعية)
      - قرار الشراء (0/1) — مُولَّد بناءً على عوامل واقعية

    المخرجات: DataFrame يحتوي على 18 عمود ميزات + عمود الهدف (purchased).
    """
    random.seed(seed)
    np.random.seed(seed)

    lands = get_all_lands()
    if not lands:
        raise ValueError("لا توجد أراضٍ في قاعدة البيانات. تأكد من استدعاء get_all_lands().")

    records = []

    for _ in range(n_samples):
        # اختيار أرض عشوائية (مع تحيّز نحو الأراضي الأعلى جودة)
        weights = np.array([
            _QUALITY_NUMERIC.get(l.get("تصنيف_الجودة", "B"), 1.0) for l in lands
        ])
        weights = weights / weights.sum()
        land = lands[np.random.choice(len(lands), p=weights)]

        # توليد معايير مستثمر عشوائية
        criteria_activity = random.choice(_ACTIVITY_TYPES) if random.random() < 0.8 else None
        criteria_max_price = random.choice([
            500, 1000, 2000, 3000, 5000, 8000, 10000, 15000, 20000
        ]) if random.random() < 0.7 else None
        criteria_min_area = random.choice([
            10_000, 50_000, 100_000, 150_000, 200_000, 300_000, 500_000
        ]) if random.random() < 0.7 else None
        criteria_utilities = random.sample(
            ALL_UTILITIES, k=random.randint(0, len(ALL_UTILITIES))
        ) if random.random() < 0.6 else []
        criteria_governorate = random.choice(_GOVERNORATES) if random.random() < 0.5 else None
        criteria_min_quality = random.choice(["AAA", "AA", "A", "B"]) if random.random() < 0.5 else None
        criteria_auction_pref = random.random() < 0.3
        criteria_budget = random.choice([
            50_000_000, 100_000_000, 250_000_000, 500_000_000, 1_000_000_000, 2_000_000_000
        ]) if random.random() < 0.5 else None

        # استخراج الميزات
        features = extract_features(
            land=land,
            criteria_activity=criteria_activity,
            criteria_max_price=criteria_max_price,
            criteria_min_area=criteria_min_area,
            criteria_utilities=criteria_utilities,
            criteria_governorate=criteria_governorate,
            criteria_min_quality=criteria_min_quality,
            criteria_auction_pref=criteria_auction_pref,
            criteria_budget=criteria_budget,
        )

        # ── محاكاة قرار الشراء ──
        # الاحتمال الأساسي يعتمد على ميزات التفاعل الرئيسية
        activity_match = features[10]
        area_ratio = features[11]
        price_ratio = features[12]
        utility_cov = features[13]
        gov_match = features[14]
        quality_gap = features[15]
        auction_match = features[16]
        budget_fit = features[17]

        # درجة خام للشراء (0-1)
        raw_prob = (
            activity_match * 0.30 +          # تطابق النشاط: أهم عامل
            price_ratio * 0.20 +             # ملاءمة السعر
            area_ratio * 0.15 +              # كفاية المساحة
            utility_cov * 0.12 +             # تغطية المرافق
            budget_fit * 0.10 +              # ملاءمة الميزانية
            gov_match * 0.05 +               # المحافظة
            (quality_gap + 1) / 2 * 0.05 +   # جودة الأرض
            auction_match * 0.03             # المزاد
        )

        # إضافة ضوضاء واقعية (لأن السلوك البشري غير مثالي)
        noise = np.random.normal(0, 0.12)
        raw_prob = np.clip(raw_prob + noise, 0.0, 1.0)

        # تحديد القرار: عتبة متغيرة (تحاكي واقع أن بعض المستثمرين أكثر حرجاً)
        threshold = random.choice([0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65])
        purchased = 1 if raw_prob >= threshold else 0

        # بناء الصف
        row = {
            "activity_match": features[10],
            "area_ratio": features[11],
            "price_ratio": features[12],
            "utility_coverage": features[13],
            "governorate_match": features[14],
            "quality_gap": features[15],
            "auction_match": features[16],
            "budget_fit": features[17],
            "log_area": features[0],
            "log_price_sqm": features[1],
            "log_total_price": features[2],
            "util_count_norm": features[3],
            "quality_numeric": features[4],
            "highway_proximity": features[5],
            "port_proximity": features[6],
            "electricity_norm": features[7],
            "market_direction": features[8],
            "is_auction": features[9],
            "purchased": purchased,
        }
        records.append(row)

    df = pd.DataFrame(records)
    logger.info(
        "تم توليد بيانات تدريب: %d صف | إيجابيات: %d (%.1f%%) | سلبيات: %d (%.1f%%)",
        len(df),
        df["purchased"].sum(),
        df["purchased"].mean() * 100,
        (df["purchased"] == 0).sum(),
        (df["purchased"] == 0).mean() * 100,
    )
    return df


# ──────────────────────────────────────────────────────────────
# محرك التسجيل بالتعلم الآلي
# ──────────────────────────────────────────────────────────────

@dataclass
class TrainingReport:
    """تقرير نتائج التدريب."""
    model_type: str = ""
    n_samples: int = 0
    n_features: int = 0
    train_accuracy: float = 0.0
    test_accuracy: float = 0.0
    train_auc: float = 0.0
    test_auc: float = 0.0
    feature_importance: Dict[str, float] = field(default_factory=dict)
    class_distribution: Dict[str, int] = field(default_factory=dict)
    saved_to: str = ""


class MLScoreEngine:
    """
    محرك تسجيل التوافق المعزز بالتعلم الآلي.

    يجمع بين نموذج GradientBoosting (60%) ونظام القواعد المرجّحة (40%)
    لإنتاج نسبة توافق متكيفة (0-100%).

    الاستخدام:
        engine = MLScoreEngine()
        engine.train(historical_data)        # تدريب على بيانات سابقة
        score = engine.predict_score(land, criteria)  # توقع التوافق
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        تهيئة المحرك.

        المعاملات:
            model_path: مسار نموذج مدرب مسبقاً. إذا لم يُحدد،
                        يبحث في المسار الافتراضي ويُدرِّب نموذجاً تجريبياً إن لم يُوجد.
        """
        self._model = None
        self._feature_importance: Dict[str, float] = {}
        self._is_trained = False
        self._model_path = model_path or _MODEL_PATH

        # محاولة تحميل نموذج مدرب مسبقاً
        if self._load_model():
            logger.info("تم تحميل النموذج المدرب من: %s", self._model_path)
        else:
            logger.info(
                "لم يُعثر على نموذج مدرب. "
                "استدعِ train() لتدريب نموذج جديد أو predict_score() سيستخدم القواعد فقط."
            )

    # ──────────────────────────────────────────────────────────
    # التدريب
    # ──────────────────────────────────────────────────────────

    def train(
        self,
        historical_data: Optional[pd.DataFrame] = None,
        n_synthetic: int = 5000,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> TrainingReport:
        """
        تدريب نموذج التسجيل.

        المعاملات:
            historical_data: DataFrame يحتوي على معاملات سابقة.
                             إذا لم يُحدد، يُولَّد بيانات تجريبية من land_database.
            n_synthetic:     عدد الصفوف المُولَّدة إن لم يُمرَّر historical_data.
            test_size:       نسبة مجموعة الاختبار (الافتراضي 20%).
            random_state:    بذرة العشوائية.

        المخرجات:
            TrainingReport يحتوي على مقاييس الأداء.
        """
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, roc_auc_score

        # تحضير البيانات
        if historical_data is None:
            logger.info("لم يتم تمرير بيانات — توليد %d صف تجريبي من land_database...", n_synthetic)
            df = generate_training_data(n_samples=n_synthetic, seed=random_state)
        else:
            df = historical_data.copy()
            logger.info("استخدام البيانات الممررة: %d صف", len(df))

        # التحقق من وجود عمود الهدف
        if "purchased" not in df.columns:
            raise ValueError("DataFrame يجب أن يحتوي على عمود 'purchased' (0/1).")

        # فصل الميزات والهدف
        feature_cols = [c for c in df.columns if c != "purchased"]
        X = df[feature_cols].values
        y = df["purchased"].values

        # تقسيم تدريب/اختبار
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y,
        )

        # تدريب GradientBoosting
        self._model = GradientBoostingClassifier(
            n_estimators=120,
            max_depth=5,
            min_samples_split=15,
            min_samples_leaf=8,
            learning_rate=0.08,
            subsample=0.85,
            random_state=random_state,
        )
        self._model.fit(X_train, y_train)

        # التقييم
        y_train_pred = self._model.predict(X_train)
        y_test_pred = self._model.predict(X_test)
        y_train_proba = self._model.predict_proba(X_train)[:, 1]
        y_test_proba = self._model.predict_proba(X_test)[:, 1]

        train_acc = accuracy_score(y_train, y_train_pred)
        test_acc = accuracy_score(y_test, y_test_pred)

        # AUC (مع حماية من الفئات الأحادية في التقسيم)
        train_auc = roc_auc_score(y_train, y_train_proba) if len(set(y_train)) > 1 else 0.5
        test_auc = roc_auc_score(y_test, y_test_proba) if len(set(y_test)) > 1 else 0.5

        # أهمية الميزات
        importance_dict = {}
        for name, imp in zip(feature_cols, self._model.feature_importances_):
            importance_dict[name] = round(float(imp), 4)

        self._feature_importance = importance_dict
        self._is_trained = True

        # حفظ النموذج
        self._save_model(feature_cols)

        # توزيع الفئات
        class_dist = {
            "purchased": int(y.sum()),
            "not_purchased": int(len(y) - y.sum()),
        }

        report = TrainingReport(
            model_type="GradientBoostingClassifier",
            n_samples=len(df),
            n_features=len(feature_cols),
            train_accuracy=round(train_acc, 4),
            test_accuracy=round(test_acc, 4),
            train_auc=round(train_auc, 4),
            test_auc=round(test_auc, 4),
            feature_importance=importance_dict,
            class_distribution=class_dist,
            saved_to=self._model_path,
        )

        logger.info(
            "تم تدريب النموذج بنجاح | تدريب: %.1f%% | اختبار: %.1f%% | AUC: %.3f",
            train_acc * 100,
            test_acc * 100,
            test_auc,
        )

        return report

    # ──────────────────────────────────────────────────────────
    # التوقع
    # ──────────────────────────────────────────────────────────

    def predict_score(
        self,
        land: Dict,
        criteria_activity: Optional[str] = None,
        criteria_max_price: Optional[float] = None,
        criteria_min_area: Optional[float] = None,
        criteria_utilities: Optional[List[str]] = None,
        criteria_governorate: Optional[str] = None,
        criteria_min_quality: Optional[str] = None,
        criteria_auction_pref: bool = False,
        criteria_budget: Optional[float] = None,
    ) -> float:
        """
        توقع نسبة التوافق (0-100%) بين أرض ومعايير مستثمر.

        إذا لم يكن النموذج مدرباً، يُرجع 0.0 ويُسجَّل تحذير.
        """
        if not self._is_trained or self._model is None:
            logger.warning("النموذج غير مدرب — يُرجع 0.0. استدعِ train() أولاً.")
            return 0.0

        features = extract_features(
            land=land,
            criteria_activity=criteria_activity,
            criteria_max_price=criteria_max_price,
            criteria_min_area=criteria_min_area,
            criteria_utilities=criteria_utilities,
            criteria_governorate=criteria_governorate,
            criteria_min_quality=criteria_min_quality,
            criteria_auction_pref=criteria_auction_pref,
            criteria_budget=criteria_budget,
        )

        # إعادة ترتيب الميزات حسب ترتيب التدريب (18 ميزة بالترتيب الصحيح)
        ordered_features = np.array([
            features[10],   # activity_match
            features[11],   # area_ratio
            features[12],   # price_ratio
            features[13],   # utility_coverage
            features[14],   # governorate_match
            features[15],   # quality_gap
            features[16],   # auction_match
            features[17],   # budget_fit
            features[0],    # log_area
            features[1],    # log_price_sqm
            features[2],    # log_total_price
            features[3],    # util_count_norm
            features[4],    # quality_numeric
            features[5],    # highway_proximity
            features[6],    # port_proximity
            features[7],    # electricity_norm
            features[8],    # market_direction
            features[9],    # is_auction
        ]).reshape(1, -1)

        # احتمال الشراء من النموذج
        purchase_prob = self._model.predict_proba(ordered_features)[0, 1]
        ml_score = purchase_prob * 100.0  # تحويل إلى 0-100

        return round(min(ml_score, 100.0), 2)

    # ──────────────────────────────────────────────────────────
    # النقاط الهجينة
    # ──────────────────────────────────────────────────────────

    def get_feature_importance(self) -> Dict[str, float]:
        """إرجاع أهمية الميزات بعد التدريب."""
        return dict(self._feature_importance)

    @property
    def is_trained(self) -> bool:
        """هل النموذج مدرب وجاهز؟"""
        return self._is_trained

    # ──────────────────────────────────────────────────────────
    # حفظ / تحميل النموذج
    # ──────────────────────────────────────────────────────────

    def _save_model(self, feature_cols: List[str]) -> None:
        """حفظ النموذج وأسماء الميزات إلى القرص."""
        try:
            import joblib
            import json

            os.makedirs(_MODEL_DIR, exist_ok=True)

            joblib.dump(self._model, self._model_path, compress=3)

            with open(_FEATURE_NAMES_PATH, "w", encoding="utf-8") as f:
                json.dump(feature_cols, f, ensure_ascii=False, indent=2)

            logger.info("تم حفظ النموذج: %s", self._model_path)
        except Exception as e:
            logger.error("فشل حفظ النموذج: %s", e)

    def _load_model(self) -> bool:
        """تحميل نموذج مدرب مسبقاً من القرص."""
        try:
            import joblib

            if not os.path.exists(self._model_path):
                return False

            self._model = joblib.load(self._model_path)
            self._is_trained = True
            return True
        except Exception as e:
            logger.warning("فشل تحميل النموذج: %s", e)
            return False


# ──────────────────────────────────────────────────────────────
# دمج النظام الهجين — نقطة الدخول الموحدة
# ──────────────────────────────────────────────────────────────

def compute_hybrid_score(
    land: Dict,
    criteria,  # InvestorCriteria dataclass
    ml_engine: Optional[MLScoreEngine] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    حساب نسبة التوافق الهجينة: 60% نموذج ML + 40% قواعد.

    المعاملات:
        land:      قاموس بيانات الأرض (من land_database)
        criteria:  كائن InvestorCriteria
        ml_engine: محرك ML (يُنشأ تلقائياً إن لم يُمرَّر)

    المخرجات:
        (hybrid_score, breakdown_dict)
        - hybrid_score: النسبة الهجينة النهائية (0-100%)
        - breakdown_dict: تفصيل الدرجات (ml_score, rule_score, weights)
    """
    from core.matchmaking.service import compute_compatibility_score

    # ── 1. درجة القواعد (النظام الحالي) ──
    rule_result = compute_compatibility_score(land, criteria)
    rule_score = rule_result.compatibility_pct

    # ── 2. درجة النموذج ──
    if ml_engine is None:
        ml_engine = _get_default_engine()

    if ml_engine.is_trained:
        ml_score = ml_engine.predict_score(
            land=land,
            criteria_activity=criteria.النشاط_المطلوب,
            criteria_max_price=criteria.الحد_الأقصى_للسعر_للمتر,
            criteria_min_area=criteria.الحد_الأدنى_للمساحة,
            criteria_utilities=criteria.المرافق_المطلوبة,
            criteria_governorate=criteria.المحافظة_المفضلة,
            criteria_min_quality=criteria.الحد_الأدنى_للجودة,
            criteria_auction_pref=criteria.تفضيل_المزاد,
            criteria_budget=criteria.الميزانية_الإجمالية,
        )
    else:
        # إذا لم يكن النموذج مدرباً، نستخدم القواعد فقط
        ml_score = rule_score
        logger.debug("النموذج غير مدرب — استخدام القواعد فقط (%.1f%%)", rule_score)

    # ── 3. الدمج الهجين ──
    hybrid = ML_WEIGHT * ml_score + RULE_WEIGHT * rule_score
    hybrid = round(min(hybrid, 100.0), 1)

    breakdown = {
        "ml_score": round(ml_score, 1),
        "rule_score": round(rule_score, 1),
        "hybrid_score": hybrid,
        "ml_weight": ML_WEIGHT,
        "rule_weight": RULE_WEIGHT,
        "model_trained": ml_engine.is_trained,
    }

    return hybrid, breakdown


def investor_smart_match_hybrid(
    criteria,
    top_k: int = 10,
    min_score: float = 0.0,
    ml_engine: Optional[MLScoreEngine] = None,
) -> List:
    """
    مطابقة ذكية هجينة — نسخة محسّنة من investor_smart_match.

    تستخدم التسجيل الهجين (60% ML + 40% قواعد) بدلاً من القواعد فقط.
    تُرجع نفس هيكل MatchResult مع إضافة حقول ml_score و hybrid_score.
    """
    from core.matchmaking.service import (
        investor_smart_match,
        compute_compatibility_score,
        MatchResult,
        _QUALITY_ORDER,
    )

    lands = get_all_lands()

    if ml_engine is None:
        ml_engine = _get_default_engine()

    results: List[MatchResult] = []

    for land in lands:
        # فلتر مبدئي: الحد الأدنى للجودة
        if criteria.الحد_الأدنى_للجودة:
            land_quality = land.get("تصنيف_الجودة", "B")
            min_order = _QUALITY_ORDER.get(criteria.الحد_الأدنى_للجودة, 0)
            land_order = _QUALITY_ORDER.get(land_quality, 0)
            if land_order < min_order:
                continue

        # حساب الدرجة الهجينة
        hybrid_score, breakdown = compute_hybrid_score(land, criteria, ml_engine)

        if hybrid_score < min_score:
            continue

        # بناء النتيجة (نستخدم النتيجة القاعدية كأساس ونضيف ML)
        match = compute_compatibility_score(land, criteria)

        # تحديث التوافق بالنسبة الهجينة
        match.compatibility_pct = hybrid_score
        match.score_details["درجة_النموذج"] = breakdown["ml_score"]
        match.score_details["درجة_القواعد"] = breakdown["rule_score"]
        match.score_details["الوزن_النموذج"] = f"{ML_WEIGHT:.0%}"
        match.score_details["الوزن_القواعد"] = f"{RULE_WEIGHT:.0%}"

        # إضافة أسباب ML
        if ml_engine.is_trained:
            match.match_reasons.append(
                f"نموذج ML: {breakdown['ml_score']:.1f}% | "
                f"القواعد: {breakdown['rule_score']:.1f}% | "
                f"النهائي: {hybrid_score:.1f}%"
            )

        results.append(match)

    # ترتيب تنازلي حسب النسبة الهجينة
    results.sort(key=lambda m: m.compatibility_pct, reverse=True)
    return results[:top_k]


# ──────────────────────────────────────────────────────────────
# ذاكرة تخزين مؤقت للمحرك الافتراضي (Singleton)
# ──────────────────────────────────────────────────────────────

_default_engine: Optional[MLScoreEngine] = None


def _get_default_engine() -> MLScoreEngine:
    """إرجاع محرك ML الافتراضي (يُنشأ مرة واحدة فقط)."""
    global _default_engine
    if _default_engine is None:
        _default_engine = MLScoreEngine()
    return _default_engine


def train_default_engine(
    n_synthetic: int = 5000,
    random_state: int = 42,
) -> TrainingReport:
    """
    تدريب المحرك الافتراضي وحفظه لل.use في جميع الاستدعاءات اللاحقة.

    يُستدعى مرة واحدة عند بدء التطبيق أو عند تحديث البيانات.
    """
    global _default_engine
    _default_engine = MLScoreEngine()
    report = _default_engine.train(n_synthetic=n_synthetic, random_state=random_state)
    return report


# ──────────────────────────────────────────────────────────────
# سكربت التشغيل المباشر
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 65)
    print("  نظام التسجيل بالتعلم الآلي — تدريب وتقييم")
    print("=" * 65)
    print()

    # 1. تدريب النموذج
    print("[1/4] تدريب النموذج على بيانات تجريبية (5,000 صف)...")
    engine = MLScoreEngine()
    report = engine.train(n_synthetic=5000, random_state=42)

    print(f"\n  النموذج: {report.model_type}")
    print(f"  العينات: {report.n_samples} | الميزات: {report.n_features}")
    print(f"  دقة التدريب: {report.train_accuracy:.1%}")
    print(f"  دقة الاختبار: {report.test_accuracy:.1%}")
    print(f"  AUC التدريب: {report.train_auc:.3f}")
    print(f"  AUC الاختبار: {report.test_auc:.3f}")
    print(f"  التوزيع: {report.class_distribution}")
    print(f"  الحفظ: {report.saved_to}")

    # 2. أهمية الميزات
    print("\n[2/4] أهمية الميزات (مرتبة تنازلياً):")
    sorted_imp = sorted(report.feature_importance.items(), key=lambda x: x[1], reverse=True)
    for name, imp in sorted_imp:
        bar = "█" * int(imp * 200)
        print(f"  {name:25s} {imp:.4f}  {bar}")

    # 3. اختبار على أرض حقيقية
    print("\n[3/4] اختبار التسجيل الهجين على أراضٍ حقيقية:")
    from core.matchmaking.service import InvestorCriteria

    test_criteria = InvestorCriteria(
        النشاط_المطلوب="صناعي",
        الحد_الأقصى_للسعر_للمتر=5000,
        الحد_الأدنى_للمساحة=100_000,
        المرافق_المطلوبة=["مياه", "كهرباء", "غاز طبيعي"],
        الحد_الأدنى_للجودة="A",
        الميزانية_الإجمالية=500_000_000,
    )

    hybrid_results = investor_smart_match_hybrid(
        criteria=test_criteria,
        top_k=5,
        ml_engine=engine,
    )

    for i, r in enumerate(hybrid_results, 1):
        ml_s = r.score_details.get("درجة_النموذج", 0)
        ru_s = r.score_details.get("درجة_القواعد", 0)
        print(f"  #{i} {r.land_id} | هجين: {r.compatibility_pct:.1f}% "
              f"(ML: {ml_s:.1f}% + قواعد: {ru_s:.1f}%) | {r.land_quality_rating}")

    # 4. مقارنة القواعد فقط مقابل الهجين
    print("\n[4/4] مقارنة: قواعد فقط vs هجين:")
    from core.matchmaking.service import investor_smart_match

    rule_only = investor_smart_match(test_criteria, top_k=5)
    for ro, hy in zip(rule_only, hybrid_results):
        diff = hy.compatibility_pct - ro.compatibility_pct
        sign = "+" if diff >= 0 else ""
        print(f"  {ro.land_id}: قواعد={ro.compatibility_pct:.1f}% → "
              f"هجين={hy.compatibility_pct:.1f}% ({sign}{diff:.1f})")

    print("\n" + "=" * 65)
    print("  تم التدريب والتقييم بنجاح!")
    print("=" * 65)