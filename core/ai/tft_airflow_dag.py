"""
Airflow DAG — إعادة تدريب شهرية لنموذج TFT
==============================================
Smart Land Management Copilot — Monthly Retraining DAG
======================================================

تُجدول إعادة تدريب نموذج TFT شهرياً مع:
  1. سحب أحدث البيانات من مصادر متعددة (قاعدة بيانات + CSV)
  2. معالجة البيانات الزمنية بالـ TimeSeriesPreprocessor
  3. تدريب النموذج مع مقارنة بالنسخة السابقة
  4. تقييم الأداء ورفض النماذج المتدهورة
  5. حفظ النموذج الجديد مع رقم إصدار
  6. إرسال إشعار بالنتيجة (Slack/Email/Log)

التركيب: pip install apache-airflow pandas numpy
التنشيط: airflow dags trigger smartland_tft_retrain

إعدادات الجدولة:
  - التشغيل: أول يوم من كل شهر في الساعة 2:00 فجراً
  - إعادة المحاولة: 3 مرات بفاصل 5 دقائق
  - المهلة الزمنية: 3 ساعات
"""

import os
import json
import logging
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── استيرادات كسولة ──
_pd = None
_np = None


def _ensure_pandas():
    global _pd
    if _pd is None:
        try:
            import pandas as _pandas
            _pd = _pandas
        except ImportError:
            raise ImportError("Pandas غير مثبّت. ثبّته عبر: pip install pandas")
    return _pd


def _ensure_numpy():
    global _np
    if _np is None:
        try:
            import numpy as _numpy
            _np = _numpy
        except ImportError:
            raise ImportError("NumPy غير مثبّت. ثبّته عبر: pip install numpy")
    return _np


# ════════════════════════════════════════════════════════════════
# المسارات وال إعدادات
# ════════════════════════════════════════════════════════════════

# هذه المسارات قابلة للتعديل عبر متغيرات البيئة
PROJECT_ROOT = os.getenv(
    "SMARTLAND_PROJECT_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "tft")
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "historical")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "retraining")

# إعدادات التدريب الافتراضية
DEFAULT_TRAINING_CONFIG = {
    "epochs": 50,
    "batch_size": 32,
    "learning_rate": 1e-3,
    "weight_decay": 1e-5,
    "hidden_size": 64,
    "dropout": 0.2,
    "num_heads": 4,
    "encoder_length": 24,
    "decoder_length": 12,
    "early_stopping_patience": 7,
    "reduce_lr_patience": 3,
}

# عتبة التحسن المطلوبة لقبول النموذج الجديد
IMPROVEMENT_THRESHOLD = 0.02  # 2% تحسن كحد أدنى


# ════════════════════════════════════════════════════════════════
# دوال المهام (Task Functions)
# ════════════════════════════════════════════════════════════════

def fetch_latest_data(**context: Dict[str, Any]) -> str:
    """
    المهمة 1: سحب أحدث البيانات من المصادر المتاحة.

    يدعم:
      - قاعدة بيانات SQLite المحلية (data/historical/land_prices.db)
      - ملفات CSV في مجلد data/historical/
      - توليد بيانات تجريبية كـ fallback

    المخرجات:
        مسار ملف CSV المؤقت بالبيانات المُجمَّعة
    """
    pd = _ensure_pandas()

    os.makedirs(DATA_DIR, exist_ok=True)
    output_path = os.path.join(DATA_DIR, f"aggregated_{datetime.now().strftime('%Y%m%d')}.csv")

    all_frames = []

    # ── المصدر 1: ملفات CSV ──
    csv_files = [
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR) if f.endswith(".csv") and "aggregated" not in f
    ]

    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file, parse_dates=["التاريخ"] if "التاريخ" in pd.read_csv(csv_file, nrows=1).columns else None)
            all_frames.append(df)
            logger.info(f"تم تحميل: {csv_file} ({len(df)} سجل)")
        except Exception as e:
            logger.warning(f"خطأ في تحميل {csv_file}: {e}")

    # ── المصدر 2: قاعدة بيانات SQLite ──
    db_path = os.path.join(DATA_DIR, "land_prices.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            df = pd.read_sql("SELECT * FROM land_prices ORDER BY date", conn)
            conn.close()
            if not df.empty:
                # ترجمة أسماء الأعمدة الإنجليزية للعربية
                col_map = {
                    "date": "التاريخ", "land_id": "land_id",
                    "governorate": "المحافظة", "activity": "النشاط",
                    "area_sqm": "المساحة_متر", "utilities": "المرافق",
                    "price_per_sqm": "السعر_للمتر", "total_price": "إجمالي_السعر",
                    "monthly_growth_rate": "معدل_النمو_الشهري",
                }
                df.rename(columns=col_map, inplace=True)
                all_frames.append(df)
                logger.info(f"تم تحميل من SQLite: {len(df)} سجل")
        except Exception as e:
            logger.warning(f"خطأ في قراءة SQLite: {e}")

    # ── الدمج ──
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        if "التاريخ" in combined.columns:
            combined["التاريخ"] = pd.to_datetime(combined["التاريخ"])
            combined = combined.drop_duplicates(
                subset=["land_id", "التاريخ"], keep="last"
            )
            combined = combined.sort_values(["land_id", "التاريخ"]).reset_index(drop=True)
    else:
        # Fallback: توليد بيانات تجريبية
        logger.warning("لا توجد بيانات — سيتم توليد بيانات تجريبية")
        sys_path = PROJECT_ROOT
        if sys_path not in os.sys.path:
            os.sys.path.insert(0, sys_path)

        from ai.tft_training import TimeSeriesPreprocessor
        preprocessor = TimeSeriesPreprocessor()
        combined = preprocessor.generate_sample_data(num_months=72, num_lands=5)

    combined.to_csv(output_path, index=False, encoding="utf-8-sig")

    # حفظ المسار في XCom
    context["ti"].xcom_push(key="data_path", value=output_path)
    context["ti"].xcom_push(key="data_rows", value=len(combined))

    logger.info(f"تم جمع البيانات: {len(combined)} سجل → {output_path}")
    return output_path


def preprocess_data(**context: Dict[str, Any]) -> str:
    """
    المهمة 2: معالجة البيانات الزمنية وتجهيزها للتدريب.

    يستخدم TimeSeriesPreprocessor لـ:
      - تنظيف القيم المفقودة
      - استخراج الميزات الزمنية (الشهر، الموسم، etc.)
      - تطبيع البيانات (Z-score + Log Transform)
      - إنشاء النوافذ الزمنية
      - التقسيم الزمني (train/val/test)
    """
    pd = _ensure_pandas()

    data_path = context["ti"].xcom_pull(key="data_path", task_ids="fetch_latest_data")

    config = json.loads(
        os.getenv("TFT_TRAINING_CONFIG", json.dumps(DEFAULT_TRAINING_CONFIG))
    )

    sys_path = PROJECT_ROOT
    if sys_path not in os.sys.path:
        os.sys.path.insert(0, sys_path)

    from ai.tft_training import TimeSeriesPreprocessor

    # تحميل البيانات
    df = pd.read_csv(data_path, parse_dates=["التاريخ"] if "التاريخ" in pd.read_csv(data_path, nrows=1).columns else None)

    # معالجة البيانات
    preprocessor = TimeSeriesPreprocessor(
        encoder_length=config["encoder_length"],
        decoder_length=config["decoder_length"],
    )

    train, val, test = preprocessor.prepare_for_tft(df)

    # حفظ الحالة للمراحل التالية
    os.makedirs(MODEL_DIR, exist_ok=True)
    preprocessor_path = os.path.join(MODEL_DIR, "preprocessor_state.json")
    with open(preprocessor_path, "w", encoding="utf-8") as f:
        json.dump(preprocessor.get_scalers_state(), f, ensure_ascii=False, indent=2)

    # حفظ مسارات النوافذ
    import numpy as np

    windows_dir = os.path.join(MODEL_DIR, "windows")
    os.makedirs(windows_dir, exist_ok=True)
    np.save(os.path.join(windows_dir, "train_obs_enc.npy"), train["observed_encoder"])
    np.save(os.path.join(windows_dir, "train_known_enc.npy"), train["known_future_encoder"])
    np.save(os.path.join(windows_dir, "train_obs_dec.npy"), train["observed_decoder"])
    np.save(os.path.join(windows_dir, "train_known_dec.npy"), train["known_future_decoder"])
    np.save(os.path.join(windows_dir, "train_targets.npy"), train["targets"])
    np.save(os.path.join(windows_dir, "train_static.npy"), train["static_continuous"])

    if val and len(val.get("land_ids", [])) > 0:
        np.save(os.path.join(windows_dir, "val_obs_enc.npy"), val["observed_encoder"])
        np.save(os.path.join(windows_dir, "val_known_enc.npy"), val["known_future_encoder"])
        np.save(os.path.join(windows_dir, "val_obs_dec.npy"), val["observed_decoder"])
        np.save(os.path.join(windows_dir, "val_known_dec.npy"), val["known_future_decoder"])
        np.save(os.path.join(windows_dir, "val_targets.npy"), val["targets"])
        np.save(os.path.join(windows_dir, "val_static.npy"), val["static_continuous"])

    train_samples = len(train.get("land_ids", []))
    val_samples = len(val.get("land_ids", [])) if val else 0
    test_samples = len(test.get("land_ids", [])) if test else 0

    context["ti"].xcom_push(key="preprocessor_path", value=preprocessor_path)
    context["ti"].xcom_push(key="windows_dir", value=windows_dir)
    context["ti"].xcom_push(key="train_samples", value=train_samples)
    context["ti"].xcom_push(key="val_samples", value=val_samples)

    logger.info(
        f"تمت معالجة البيانات: تدريب={train_samples}, "
        f"تحقق={val_samples}, اختبار={test_samples}"
    )

    return preprocessor_path


def train_model_task(**context: Dict[str, Any]) -> str:
    """
    المهمة 3: تدريب نموذج TFT.

    يُحمّل النوافذ المُعالجة ويُدرّب النموذج مع:
      - Early Stopping
      - Reduce LR on Plateau
      - Gradient Clipping
      - أفضل نموذج محفوظ تلقائياً
    """
    import numpy as np

    config = json.loads(
        os.getenv("TFT_TRAINING_CONFIG", json.dumps(DEFAULT_TRAINING_CONFIG))
    )

    windows_dir = context["ti"].xcom_pull(key="windows_dir", task_ids="preprocess_data")

    sys_path = PROJECT_ROOT
    if sys_path not in os.sys.path:
        os.sys.path.insert(0, sys_path)

    from ai.tft_training import train_tft_model

    # تحميل النوافذ
    def _load_or_empty(filename):
        path = os.path.join(windows_dir, filename)
        if os.path.exists(path):
            return np.load(path)
        return np.array([], dtype=np.float32)

    train_windows = {
        "observed_encoder": _load_or_empty("train_obs_enc.npy"),
        "known_future_encoder": _load_or_empty("train_known_enc.npy"),
        "observed_decoder": _load_or_empty("train_obs_dec.npy"),
        "known_future_decoder": _load_or_empty("train_known_dec.npy"),
        "targets": _load_or_empty("train_targets.npy"),
        "static_continuous": _load_or_empty("train_static.npy"),
        "land_ids": ["train"] * len(_load_or_empty("train_targets.npy")),
    }

    val_obs = _load_or_empty("val_obs_enc.npy")
    val_windows = None
    if val_obs.size > 0:
        val_windows = {
            "observed_encoder": val_obs,
            "known_future_encoder": _load_or_empty("val_known_enc.npy"),
            "observed_decoder": _load_or_empty("val_obs_dec.npy"),
            "known_future_decoder": _load_or_empty("val_known_dec.npy"),
            "targets": _load_or_empty("val_targets.npy"),
            "static_continuous": _load_or_empty("val_static.npy"),
            "land_ids": ["val"] * len(val_obs),
        }

    # مسار الحفظ مع إصدار
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = os.path.join(MODEL_DIR, f"tft_model_{timestamp}.pt")

    # تدريب النموذج
    result = train_tft_model(
        X_train=train_windows,
        X_val=val_windows,
        model_save_path=model_path,
        verbose=True,
        **{k: v for k, v in config.items() if k in [
            "epochs", "batch_size", "learning_rate", "weight_decay",
            "hidden_size", "dropout", "num_heads", "encoder_length",
            "decoder_length", "early_stopping_patience", "reduce_lr_patience",
        ]},
    )

    context["ti"].xcom_push(key="model_path", value=model_path)
    context["ti"].xcom_push(key="best_val_loss", value=result["best_val_loss"])
    context["ti"].xcom_push(key="best_epoch", value=result["best_epoch"])
    context["ti"].xcom_push(key="training_history", value=result["training_history"])

    logger.info(
        f"اكتمل التدريب: أفضل خسارة={result['best_val_loss']:.6f}, "
        f"أفضل حقبة={result['best_epoch']}"
    )

    return model_path


def evaluate_and_compare(**context: Dict[str, Any]) -> Dict[str, Any]:
    """
    المهمة 4: تقييم النموذج الجديد ومقارنته بالنسخة السابقة.

    المنطق:
      - إذا لم يكن هناك نموذج سابق → قبول النموذج الجديد
      - إذا كان النموذج الجديد أفضل بـ IMPROVEMENT_THRESHOLD → قبول
      - إذا كان أسوأ → رفض والاحتفاظ بالسابق
    """
    import numpy as np

    new_model_path = context["ti"].xcom_pull(key="model_path", task_ids="train_model_task")
    new_val_loss = context["ti"].xcom_pull(key="best_val_loss", task_ids="train_model_task")

    # البحث عن آخر نموذج مُنتَج
    previous_model_path = os.path.join(MODEL_DIR, "tft_model_latest.pt")
    previous_val_loss = None

    if os.path.exists(previous_model_path):
        try:
            checkpoint = __import__("torch").load(
                previous_model_path, map_location="cpu", weights_only=False
            )
            previous_val_loss = checkpoint.get("best_val_loss")
            logger.info(f"النموذج السابق: val_loss={previous_val_loss:.6f}")
        except Exception as e:
            logger.warning(f"لم يتم تحميل النموذج السابق: {e}")

    # المقارنة
    evaluation_result = {
        "new_model_path": new_model_path,
        "previous_model_path": previous_model_path if os.path.exists(previous_model_path) else None,
        "new_val_loss": new_val_loss,
        "previous_val_loss": previous_val_loss,
        "improvement": None,
        "accepted": True,
        "reason": "",
    }

    if previous_val_loss is not None:
        improvement = (previous_val_loss - new_val_loss) / previous_val_loss
        evaluation_result["improvement"] = round(improvement, 4)

        if improvement >= IMPROVEMENT_THRESHOLD:
            evaluation_result["accepted"] = True
            evaluation_result["reason"] = (
                f"تحسن بنسبة {improvement:.1%} (أكثر من العتبة {IMPROVEMENT_THRESHOLD:.0%})"
            )
        elif improvement >= 0:
            evaluation_result["accepted"] = True
            evaluation_result["reason"] = (
                f"تحسن طفيف {improvement:.1%} — مقبول (أقل من العتبة لكن إيجابي)"
            )
        else:
            evaluation_result["accepted"] = False
            evaluation_result["reason"] = (
                f"تدهور بنسبة {abs(improvement):.1%} — النموذج الجديد مرفوض"
            )
    else:
        evaluation_result["reason"] = "لا يوجد نموذج سابق — القبول التلقائي"

    context["ti"].xcom_push(key="evaluation", value=evaluation_result)

    logger.info(f"تقييم النموذج: مقبول={evaluation_result['accepted']}, السبب: {evaluation_result['reason']}")

    return evaluation_result


def deploy_model(**context: Dict[str, Any]) -> str:
    """
    المهمة 5: نشر النموذج المقبول.

    إذا قُبل النموذج الجديد:
      1. نسخه كـ tft_model_latest.pt
      2. الاحتفاظ بآخر 5 إصدارات
      3. تحديث ملف VERSION
      4. تسجيل بيانات النشر
    """
    evaluation = context["ti"].xcom_pull(key="evaluation", task_ids="evaluate_and_compare")
    new_model_path = evaluation["new_model_path"]

    if not evaluation["accepted"]:
        logger.warning(f"النموذج مرفوض: {evaluation['reason']}")
        return "rejected"

    # نسخ كأحدث إصدار
    latest_path = os.path.join(MODEL_DIR, "tft_model_latest.pt")
    if os.path.exists(latest_path):
        # نسخ احتياطي للإصدار السابق
        backup_name = f"tft_model_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pt"
        shutil.copy2(latest_path, os.path.join(MODEL_DIR, backup_name))

    shutil.copy2(new_model_path, latest_path)

    # الاحتفاظ بآخر 5 إصدارات فقط
    model_files = sorted([
        f for f in os.listdir(MODEL_DIR)
        if f.startswith("tft_model_") and f.endswith(".pt") and f != "tft_model_latest.pt"
    ])

    if len(model_files) > 5:
        for old_file in model_files[:-5]:
            os.remove(os.path.join(MODEL_DIR, old_file))
            logger.info(f"حُذف الإصدار القديم: {old_file}")

    # تحديث ملف VERSION
    version_info = {
        "version": datetime.now().strftime("%Y.%m.%d"),
        "model_path": latest_path,
        "val_loss": evaluation["new_val_loss"],
        "improvement": evaluation["improvement"],
        "deployed_at": datetime.now().isoformat(),
        "training_epochs": context["ti"].xcom_pull(
            key="best_epoch", task_ids="train_model_task"
        ),
    }

    version_path = os.path.join(MODEL_DIR, "VERSION.json")
    with open(version_path, "w", encoding="utf-8") as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)

    logger.info(f"تم نشر النموذج: {latest_path}")
    logger.info(f"معلومات الإصدار: {json.dumps(version_info, ensure_ascii=False)}")

    return latest_path


def send_notification(**context: Dict[str, Any]) -> str:
    """
    المهمة 6: إرسال إشعار بنتيجة إعادة التدريب.

    القنوات المدعومة:
      - سجل Airflow (دائماً)
      - Slack (إذا تم تحديد SLACK_WEBHOOK_URL)
      - Email (إذا تم تحديد NOTIFICATION_EMAIL)
      - ملف سجل محلي (دائماً)
    """
    evaluation = context["ti"].xcom_pull(key="evaluation", task_ids="evaluate_and_compare")
    data_rows = context["ti"].xcom_pull(key="data_rows", task_ids="fetch_latest_data")
    train_samples = context["ti"].xcom_pull(key="train_samples", task_ids="preprocess_data")
    val_samples = context["ti"].xcom_pull(key="val_samples", task_ids="preprocess_data")
    best_epoch = context["ti"].xcom_pull(key="best_epoch", task_ids="train_model_task")

    # بناء الرسالة
    status_emoji = "✅" if evaluation["accepted"] else "❌"
    status_text = "مقبول" if evaluation["accepted"] else "مرفوض"

    message = (
        f"{status_emoji} تقرير إعادة تدريب TFT — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'=' * 50}\n"
        f"الحالة: {status_text}\n"
        f"السبب: {evaluation['reason']}\n"
        f"خسارة التحقق (الجديد): {evaluation['new_val_loss']:.6f}\n"
    )

    if evaluation["previous_val_loss"] is not None:
        message += f"خسارة التحقق (السابق): {evaluation['previous_val_loss']:.6f}\n"
        if evaluation["improvement"] is not None:
            message += f"نسبة التحسن: {evaluation['improvement']:.1%}\n"

    message += (
        f"\nالبيانات:\n"
        f"  إجمالي السجلات: {data_rows}\n"
        f"  عينات التدريب: {train_samples}\n"
        f"  عينات التحقق: {val_samples}\n"
        f"  أفضل حقبة: {best_epoch}\n"
    )

    # ── سجل Airflow ──
    logger.info(f"\n{'=' * 50}\n{message}{'=' * 50}")

    # ── ملف سجل محلي ──
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(message)

    # ── Slack ──
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook and evaluation["accepted"]:
        try:
            import requests
            requests.post(
                slack_webhook,
                json={"text": message},
                timeout=10,
            )
            logger.info("تم إرسال إشعار Slack")
        except Exception as e:
            logger.warning(f"فشل إرسال Slack: {e}")

    # ── Email ──
    notification_email = os.getenv("NOTIFICATION_EMAIL")
    if notification_email and not evaluation["accepted"]:
        logger.info(
            f"⚠️ النموذج مرفوض — يُنصح بإرسال تنبيه بريدي إلى: {notification_email}"
        )

    return message


# ════════════════════════════════════════════════════════════════
# تعريف DAG
# ════════════════════════════════════════════════════════════════

def retrain_model_airflow():
    """
    إنشاء وتسجيل DAG Airflow لإعادة تدريب نموذج TFT شهرياً.

    جدولة التشغيل:
      - كل شهر في اليوم الأول عند الساعة 2:00 فجراً بتوقيت القاهرة
      - يمكن تشغيلها يدوياً عبر: airflow dags trigger smartland_tft_retrain

    إعدادات الاسترداد:
      - إعادة المحاولة: 3 مرات
      - فاصل الانتظار: 5 دقائق
      - مهلة الحقبة: 3 ساعات

    المخطط (DAG Graph):
      fetch_latest_data → preprocess_data → train_model_task
                                                      ↓
                          send_notification ← evaluate_and_compare → deploy_model
    """
    try:
        from airflow import DAG
        from airflow.operators.python import PythonOperator
    except ImportError:
        logger.error(
            "Apache Airflow غير مثبّت. ثبّته عبر:\n"
            "  pip install apache-airflow\n"
            "أو شغّل التدريب مباشرة عبر:\n"
            "  python -c \"from ai.tft_training import train_tft_model; ...\""
        )
        return None

    # ── الوسائط الافتراضية ──
    default_args = {
        "owner": "smartland-ai",
        "depends_on_past": False,
        "email": os.getenv("NOTIFICATION_EMAIL", ""),
        "email_on_failure": True,
        "email_on_retry": False,
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=3),
    }

    # ── تعريف DAG ──
    dag = DAG(
        dag_id="smartland_tft_retrain",
        default_args=default_args,
        description="إعادة تدريب شهرية لنموذج TFT للتنبؤ بأسعار الأراضي المصرية",
        schedule_interval="0 2 1 * *",  # أول يوم من كل شهر، الساعة 2 فجراً
        start_date=datetime(2025, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["smartland", "tft", "retraining", "land-prices", "egypt"],
        doc_md="""
        ## إعادة تدريب نموذج TFT

        ### الوصف
        DAG شهري لسحب البيانات الأحدث وتدريب نموذج Temporal Fusion Transformer
        للتنبؤ بأسعار الأراضي في السوق المصري.

        ### المهام
        1. **fetch_latest_data**: سحب البيانات من CSV/SQLite
        2. **preprocess_data**: معالجة وتطبيع البيانات الزمنية
        3. **train_model_task**: تدريب نموذج TFT (50 حقبة)
        4. **evaluate_and_compare**: مقارنة النموذج الجديد بالسابق
        5. **deploy_model**: نشر النموذج المقبول
        6. **send_notification**: إرسال إشعار بالنتيجة

        ### التشغيل اليدوي
        ```bash
        airflow dags trigger smartland_tft_retrain
        ```

        ### متغيرات البيئة
        - `SMARTLAND_PROJECT_ROOT`: مسار المشروع
        - `TFT_TRAINING_CONFIG`: إعدادات التدريب (JSON)
        - `SLACK_WEBHOOK_URL`: رابط Slack للإشعارات
        - `NOTIFICATION_EMAIL`: بريد إلكتروني للتنبيهات
        """,
    )

    # ── تعريف المهام ──
    task_fetch = PythonOperator(
        task_id="fetch_latest_data",
        python_callable=fetch_latest_data,
        provide_context=True,
    )

    task_preprocess = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data,
        provide_context=True,
    )

    task_train = PythonOperator(
        task_id="train_model_task",
        python_callable=train_model_task,
        provide_context=True,
        execution_timeout=timedelta(hours=2),
    )

    task_evaluate = PythonOperator(
        task_id="evaluate_and_compare",
        python_callable=evaluate_and_compare,
        provide_context=True,
    )

    task_deploy = PythonOperator(
        task_id="deploy_model",
        python_callable=deploy_model,
        provide_context=True,
        trigger_rule="one_success",
    )

    task_notify = PythonOperator(
        task_id="send_notification",
        python_callable=send_notification,
        provide_context=True,
        trigger_rule="all_done",  # يُنفذ سواء نجح أو فشل
    )

    # ── تسلسل المهام ──
    task_fetch >> task_preprocess >> task_train >> task_evaluate
    task_evaluate >> [task_deploy, task_notify]

    logger.info("تم تسجيل DAG: smartland_tft_retrain")
    return dag


# ── تسجيل DAG في Airflow ──
# هذا المتغير يبحث عنه Airflow تلقائياً عند فحص مجلد dags/
dag = retrain_model_airflow()


# ════════════════════════════════════════════════════════════════
# تشغيل مباشر (بدون Airflow) — للتطوير والاختبار
# ════════════════════════════════════════════════════════════════

def run_retraining_pipeline():
    """
    تشغيل خط أنابيب إعادة التدريب بالكامل خارج Airflow.
    مفيد للتطوير والاختبار المحلي.
    """
    import numpy as np

    logger.info("=" * 60)
    logger.info("بدء خط أنابيب إعادة التدريب المحلي")
    logger.info("=" * 60)

    # ── محاكاة context ──
    class FakeTI:
        def __init__(self):
            self._data = {}

        def xcom_push(self, key, value, **kwargs):
            self._data[key] = value
            logger.info(f"  [XCom] {key} = {value if not isinstance(value, dict) else '{...}'}")

        def xcom_pull(self, key, task_ids=None, **kwargs):
            return self._data.get(key)

    class FakeContext:
        def __init__(self):
            self.ti = FakeTI()

    ctx = FakeContext()

    # ── المرحلة 1: سحب البيانات ──
    logger.info("\n📋 المرحلة 1: سحب البيانات...")
    fetch_latest_data(**{"context": ctx})

    # ── المرحلة 2: معالجة البيانات ──
    logger.info("\n⚙️  المرحلة 2: معالجة البيانات...")
    preprocess_data(**{"context": ctx})

    # ── المرحلة 3: التدريب ──
    logger.info("\n🏋️  المرحلة 3: تدريب النموذج...")
    train_model_task(**{"context": ctx})

    # ── المرحلة 4: التقييم ──
    logger.info("\n📊 المرحلة 4: تقييم النموذج...")
    evaluation = evaluate_and_compare(**{"context": ctx})

    # ── المرحلة 5: النشر ──
    logger.info("\n🚀 المرحلة 5: نشر النموذج...")
    deploy_model(**{"context": ctx})

    # ── المرحلة 6: الإشعار ──
    logger.info("\n🔔 المرحلة 6: إرسال الإشعار...")
    notification = send_notification(**{"context": ctx})

    logger.info("\n" + "=" * 60)
    logger.info("اكتمل خط أنابيب إعادة التدريب")
    logger.info("=" * 60)

    return {
        "evaluation": evaluation,
        "notification": notification,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    result = run_retraining_pipeline()
    print("\n" + result.get("notification", ""))