"""
Smart Land Copilot — Free AI Recommendation Engine
====================================================
يستخدم Groq API (مجاني) أو Ollama (محلي ومجاني) لتقديم:
1. وصف إعلاني مخصص للأرض
2. توصيات استثمارية للمشتري بناءً على السعر والمحافظة

المتطلبات:
    - pip install groq  (أو استخدام Ollama المحلي)
    - GROQ_API_KEY في متغيرات البيئة (اختياري — يعمل بدونها مع وضع تجريبي)

الإعدادات:
    - AI_PROVIDER: "groq" (افتراضي), "ollama", أو "mock" (تجريبي)
    - GROQ_API_KEY: مفتاح Groq API (مجاني من console.groq.com)
    - OLLAMA_BASE_URL: رابط خادم Ollama المحلي (افتراضي: http://localhost:11434)
    - AI_MODEL: نموذج الذكاء الاصطناعي (llama3-70b-8192, mixtral-8x7b-32768, إلخ)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# الإعدادات
# ──────────────────────────────────────────────

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")  # groq, ollama, mock
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
AI_MODEL = os.getenv("AI_MODEL", "llama3-70b-8192")  # Groq models
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")  # Ollama models

# ──────────────────────────────────────────────
# قالب التوصية
# ──────────────────────────────────────────────

@dataclass
class LandRecommendation:
    """توصية كاملة للأرض."""
    land_id: str
    governorate: str
    region_city: str = ""
    price_per_sqm_egp: float = 0.0
    total_price_egp: float = 0.0
    total_area_sqm: float = 0.0

    # مخرجات AI
    ad_description: str = ""  # وصف إعلاني جاهز
    investment_tip: str = ""  # نصيحة استثمارية
    expected_roi_pct: float = 0.0  # العائد المتوقع
    risk_level: str = "متوسط"  # منخفض، متوسط، مرتفع
    confidence_score: float = 0.0  # 0-100

    # بيانات إضافية
    comparable_avg_price: float = 0.0  # متوسط سعر المحافظة
    price_position: str = ""  # أقل من المتوسط، متوسط، أعلى من المتوسط

    ai_provider_used: str = ""
    raw_response: str = ""


# ──────────────────────────────────────────────
# 1. دالة الحصول على توصية ذكية
# ──────────────────────────────────────────────

async def get_smart_recommendation(
    land_id: str,
    user_id: str,
    governorate: str = "",
    region_city: str = "",
    price_per_sqm_egp: float = 0.0,
    total_price_egp: float = 0.0,
    total_area_sqm: float = 0.0,
    comparable_avg_price: Optional[float] = None,
) -> LandRecommendation:
    """
    الحصول على توصية ذكية للأرض باستخدام AI مجاني.

    Args:
        land_id: معرف الأرض
        user_id: معرف المستخدم
        governorate: المحافظة
        region_city: المدينة/المنطقة
        price_per_sqm_egp: سعر المتر المربع
        total_price_egp: السعر الإجمالي
        total_area_sqm: المساحة الكلية
        comparable_avg_price: متوسط أسعار المحافظة (اختياري)

    Returns:
        LandRecommendation مع التوصية الكاملة
    """
    # إنشاء كائن التوصية
    rec = LandRecommendation(
        land_id=land_id,
        governorate=governorate,
        region_city=region_city,
        price_per_sqm_egp=price_per_sqm_egp,
        total_price_egp=total_price_egp,
        total_area_sqm=total_area_sqm,
    )

    # حساب متوسط السعر إن لم يكن متاحاً
    if comparable_avg_price is None:
        comparable_avg_price = _estimate_avg_price(governorate)

    rec.comparable_avg_price = comparable_avg_price

    # تحديد موقع السعر بالنسبة للمتوسط
    if comparable_avg_price > 0:
        ratio = price_per_sqm_egp / comparable_avg_price
        if ratio < 0.85:
            rec.price_position = "أقل من متوسط سعر المحافظة"
        elif ratio < 1.15:
            rec.price_position = "في حدود متوسط سعر المحافظة"
        else:
            rec.price_position = "أعلى من متوسط سعر المحافظة"

    # استدعاء AI
    if AI_PROVIDER == "groq" and GROQ_API_KEY:
        rec = await _call_groq_api(rec)
    elif AI_PROVIDER == "ollama":
        rec = await _call_ollama(rec)
    else:
        # وضع تجريبي — يولد توصيات بدون API
        rec = _generate_mock_recommendation(rec)

    # إضافة نصيحة استثمارية احتياطية إن لم يولدها AI
    if not rec.investment_tip:
        rec.investment_tip = _generate_fallback_tip(rec)

    return rec


# ──────────────────────────────────────────────
# 2. Groq API (مجاني وسريع)
# ──────────────────────────────────────────────

async def _call_groq_api(rec: LandRecommendation) -> LandRecommendation:
    """
    استدعاء Groq API لتوليد توصية.
    Groq يقدم API مجاني مع نماذج سريعة جداً.
    """
    rec.ai_provider_used = "groq"
    system_prompt = (
        "أنت خبير عقاري مصري متخصص في الاستثمار في الأراضي. "
        "قم بتقديم توصية استثمارية دقيقة ومخصصة للأرض بناءً على بياناتها. "
        "يجب أن تكون الإجابة باللغة العربية الفصحى المبسطة."
    )

    user_prompt = f"""
    أرض للاستثمار:
    - الموقع: {rec.governorate}
    - المنطقة: {rec.region_city or 'غير محدد'}
    - المساحة: {rec.total_area_sqm:,.0f} متر مربع
    - سعر المتر: {rec.price_per_sqm_egp:,.0f} ج.م
    - السعر الإجمالي: {rec.total_price_egp:,.0f} ج.م
    - متوسط سعر المحافظة: {rec.comparable_avg_price:,.0f} ج.م/م²

    المطلوب (ردّ بجملة واحدة فقط لكل قسم):
    1. وصف إعلاني جذاب للأرض (جملة واحدة)
    2. نصيحة استثمارية للمشتري (جملة واحدة)
    3. العائد المتوقع على الاستثمار كنسبة مئوية (رقم فقط)
    4. مستوى المخاطرة (منخفض/متوسط/مرتفع)
    """

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 300,
                },
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                rec.raw_response = content
                _parse_ai_response(rec, content)
                logger.info(f"Groq API success for land {rec.land_id}")
            else:
                logger.warning(f"Groq API error: {response.status_code}")
                # الرجوع إلى الوضع التجريبي
                mock = _generate_mock_recommendation(rec)
                rec.ad_description = mock.ad_description
                rec.investment_tip = mock.investment_tip
                rec.expected_roi_pct = mock.expected_roi_pct
                rec.risk_level = mock.risk_level

    except ImportError:
        logger.warning("httpx not installed — using mock recommendation")
        mock = _generate_mock_recommendation(rec)
        rec.ad_description = mock.ad_description
        rec.investment_tip = mock.investment_tip
        rec.expected_roi_pct = mock.expected_roi_pct
        rec.risk_level = mock.risk_level
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        mock = _generate_mock_recommendation(rec)
        rec.ad_description = mock.ad_description
        rec.investment_tip = mock.investment_tip
        rec.expected_roi_pct = mock.expected_roi_pct
        rec.risk_level = mock.risk_level

    return rec


# ──────────────────────────────────────────────
# 3. Ollama (محلي ومجاني تماماً)
# ──────────────────────────────────────────────

async def _call_ollama(rec: LandRecommendation) -> LandRecommendation:
    """
    استدعاء Ollama المحلي لتوليد التوصيات.
    مجاني تماماً، يعمل دون اتصال بالإنترنت.
    """
    rec.ai_provider_used = "ollama"
    prompt = f"""
    أنت خبير عقاري. قدم توصية للأرض التالية:
    الموقع: {rec.governorate}
    المساحة: {rec.total_area_sqm:,.0f} م²
    سعر المتر: {rec.price_per_sqm_egp:,.0f} ج.م

    أجب بالعربية:
    1. وصف إعلاني
    2. نصيحة استثمارية
    3. العائد المتوقع (%)
    4. مستوى المخاطرة
    """

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("response", "")
                rec.raw_response = content
                _parse_ai_response(rec, content)
                logger.info(f"Ollama success for land {rec.land_id}")
            else:
                logger.warning(f"Ollama error: {response.status_code}")
                mock = _generate_mock_recommendation(rec)
                rec.ad_description = mock.ad_description
                rec.investment_tip = mock.investment_tip

    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        mock = _generate_mock_recommendation(rec)
        rec.ad_description = mock.ad_description
        rec.investment_tip = mock.investment_tip

    return rec


# ──────────────────────────────────────────────
# 4. تحليل رد AI
# ──────────────────────────────────────────────

def _parse_ai_response(rec: LandRecommendation, content: str):
    """استخراج المعلومات من رد AI."""
    lines = content.strip().split("\n")

    for line in lines:
        line = line.strip()

        # وصف إعلاني
        if not rec.ad_description and ("وصف" in line or "إعلان" in line):
            parts = line.split(":", 1)
            if len(parts) > 1:
                rec.ad_description = parts[1].strip()
            else:
                rec.ad_description = line

        # نصيحة استثمارية
        if not rec.investment_tip and ("نصيحة" in line or "استثمار" in line):
            parts = line.split(":", 1)
            if len(parts) > 1:
                rec.investment_tip = parts[1].strip()
            else:
                rec.investment_tip = line

        # العائد المتوقع
        if rec.expected_roi_pct == 0.0 and ("عائد" in line or "%" in line):
            import re
            numbers = re.findall(r"[\d.]+", line)
            if numbers:
                try:
                    rec.expected_roi_pct = float(numbers[0])
                except ValueError:
                    pass

        # مستوى المخاطرة
        if rec.risk_level == "متوسط" and ("مخاطرة" in line or "risk" in line.lower()):
            if "منخفض" in line:
                rec.risk_level = "منخفض"
            elif "مرتفع" in line:
                rec.risk_level = "مرتفع"
            else:
                rec.risk_level = "متوسط"

    # إنشاء وصف افتراضي إن لم يتم استخراجه
    if not rec.ad_description:
        rec.ad_description = (
            f"فرصة استثمارية فريدة في {rec.governorate}. "
            f"أرض بمساحة {rec.total_area_sqm:,.0f} متر مربع "
            f"بسعر تنافسي {rec.price_per_sqm_egp:,.0f} ج.م للمتر."
        )

    if not rec.investment_tip:
        rec.investment_tip = _generate_fallback_tip(rec)


# ──────────────────────────────────────────────
# 5. الوضع التجريبي (بدون API)
# ──────────────────────────────────────────────

def _generate_mock_recommendation(rec: LandRecommendation) -> LandRecommendation:
    """توليد توصية تجريبية بدون استدعاء API."""
    rec.ai_provider_used = "mock"

    # تقدير العائد حسب المحافظة
    roi_map = {
        "القاهرة": (12, 18),
        "الجيزة": (10, 16),
        "الإسكندرية": (10, 15),
        "السويس": (8, 14),
        "الأقصر": (7, 12),
        "أسوان": (6, 11),
        "الغردقة": (9, 15),
        "شرم الشيخ": (8, 14),
        "بورسعيد": (9, 13),
        "دمياط": (7, 12),
    }
    roi_range = roi_map.get(rec.governorate, (5, 10))

    # حساب العائد بناءً على السعر
    if rec.price_per_sqm_egp > 0 and rec.comparable_avg_price > 0:
        price_ratio = rec.price_per_sqm_egp / max(rec.comparable_avg_price, 1)
        if price_ratio < 0.8:
            expected_roi = roi_range[1]  # سعر منخفض = عائد أعلى
            rec.risk_level = "منخفض"
        elif price_ratio < 1.2:
            expected_roi = (roi_range[0] + roi_range[1]) / 2
            rec.risk_level = "متوسط"
        else:
            expected_roi = roi_range[0]  # سعر مرتفع = عائد أقل
            rec.risk_level = "مرتفع"
    else:
        expected_roi = (roi_range[0] + roi_range[1]) / 2

    rec.expected_roi_pct = round(expected_roi, 1)
    rec.confidence_score = 75.0

    # وصف إعلاني
    location_desc = {
        "القاهرة": "عاصمة مصر وقلبها النابض",
        "الجيزة": "مدينة الأهرامات والتاريخ",
        "الإسكندرية": "عروس البحر المتوسط",
        "السويس": "بوابة قناة السويس",
        "الأقصر": "مدينة الآثار الفرعونية",
        "أسوان": "جنوب مصر الساحر",
        "الغردقة": "جوهرة البحر الأحمر",
        "شرم الشيخ": "مدينة السلام والسياحة",
    }.get(rec.governorate, f"محافظة {rec.governorate}")

    rec.ad_description = (
        f"🌟 استثمار ذكي في {rec.governorate} — {location_desc}. "
        f"أرض بمساحة {rec.total_area_sqm:,.0f} متر مربع "
        f"بسعر {rec.price_per_sqm_egp:,.0f} ج.م/م². "
        f"عائد متوقع {rec.expected_roi_pct}%."
    )

    # نصيحة استثمارية
    rec.investment_tip = _generate_fallback_tip(rec)

    return rec


def _generate_fallback_tip(rec: LandRecommendation) -> str:
    """توليد نصيحة استثمارية احتياطية."""
    price_per_sqm = rec.price_per_sqm_egp
    area = rec.total_area_sqm

    if rec.risk_level == "منخفض":
        return (
            f"استثمار آمن في {rec.governorate} بسعر مناسب "
            f"({price_per_sqm:,.0f} ج.م/م²). يُنصح بالشراء للتطوير السكني "
            f"أو التجاري مع عائد متوقع {rec.expected_roi_pct}% خلال 3-5 سنوات."
        )
    elif rec.risk_level == "مرتفع":
        return (
            f"فرصة استثمارية واعدة في {rec.governorate} بمساحة {area:,.0f}م². "
            f"السعر أعلى من المتوسط لذا يُنصح بدراسة السوق جيداً. "
            f"العائد المتوقع {rec.expected_roi_pct}%."
        )
    else:
        return (
            f"فرصة استثمارية جيدة في {rec.governorate}. "
            f"السعر ضمن النطاق السعري الطبيعي للمنطقة. "
            f"يُنصح بالاستثمار على المدى المتوسط (3-7 سنوات) "
            f"لتحقيق عائد {rec.expected_roi_pct}%."
        )


def _estimate_avg_price(governorate: str) -> float:
    """تقدير متوسط سعر المتر للمحافظة (بيانات تقريبية 2025)."""
    avg_prices = {
        "القاهرة": 8000,
        "الجيزة": 6000,
        "الإسكندرية": 5500,
        "السويس": 3500,
        "الأقصر": 2500,
        "أسوان": 2000,
        "الغردقة": 7000,
        "شرم الشيخ": 6500,
        "بورسعيد": 4000,
        "دمياط": 3000,
        "المنصورة": 3500,
        "طنطا": 3000,
    }
    return avg_prices.get(governorate, 4000)


# ──────────────────────────────────────────────
# 6. فحص صحة AI
# ──────────────────────────────────────────────

async def ai_health_check() -> Dict[str, Any]:
    """فحص صحة مزود AI."""
    health = {
        "provider": AI_PROVIDER,
        "status": "unknown",
        "model": AI_MODEL,
    }

    if AI_PROVIDER == "groq":
        if GROQ_API_KEY:
            health["status"] = "configured"
            health["api_key_set"] = bool(GROQ_API_KEY)
            health["api_key_prefix"] = GROQ_API_KEY[:8] + "..." if GROQ_API_KEY else ""
        else:
            health["status"] = "not_configured"
            health["message"] = "Set GROQ_API_KEY environment variable"
        health["model"] = AI_MODEL

    elif AI_PROVIDER == "ollama":
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                if response.status_code == 200:
                    health["status"] = "connected"
                    models = response.json().get("models", [])
                    health["available_models"] = [m["name"] for m in models]
                else:
                    health["status"] = "error"
                    health["message"] = f"HTTP {response.status_code}"
        except Exception as e:
            health["status"] = "unreachable"
            health["message"] = str(e)
        health["model"] = OLLAMA_MODEL

    else:  # mock
        health["status"] = "mock"
        health["message"] = "Using mock recommendations (no AI API required)"

    return health


# ──────────────────────────────────────────────
# تشغيل اختباري
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 60)
        print("  اختبار محرك التوصيات الذكية")
        print("=" * 60)

        # فحص الصحة
        print("\n1. فحص صحة AI:")
        health = await ai_health_check()
        print(f"   Provider: {health['provider']}")
        print(f"   Status:   {health['status']}")
        print(f"   Model:    {health['model']}")

        # اختبار التوصية
        print("\n2. توصية لأرض في القاهرة:")
        rec = await get_smart_recommendation(
            land_id="LAND-CAI-001",
            user_id="INV-001",
            governorate="القاهرة",
            region_city="التجمع الخامس",
            price_per_sqm_egp=5500.0,
            total_price_egp=27_500_000.0,
            total_area_sqm=5000,
        )
        print(f"   المصدر:     {rec.ai_provider_used}")
        print(f"   الوصف:      {rec.ad_description}")
        print(f"   النصيحة:    {rec.investment_tip}")
        print(f"   العائد:     {rec.expected_roi_pct}%")
        print(f"   المخاطرة:   {rec.risk_level}")
        print(f"   الموقع:     {rec.price_position}")

        # اختبار توصية لمحافظة أخرى
        print("\n3. توصية لأرض في أسوان:")
        rec2 = await get_smart_recommendation(
            land_id="LAND-ASW-001",
            user_id="INV-002",
            governorate="أسوان",
            region_city="غرب أسوان",
            price_per_sqm_egp=1500.0,
            total_price_egp=7_500_000.0,
            total_area_sqm=5000,
        )
        print(f"   المصدر:     {rec2.ai_provider_used}")
        print(f"   الوصف:      {rec2.ad_description}")
        print(f"   النصيحة:    {rec2.investment_tip}")
        print(f"   العائد:     {rec2.expected_roi_pct}%")
        print(f"   المخاطرة:   {rec2.risk_level}")

        print("\n✅ اختبار AI مكتمل!")

    asyncio.run(test())