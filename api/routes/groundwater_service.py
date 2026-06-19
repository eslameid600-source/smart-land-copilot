"""
Groundwater Data Service
==========================
استخراج بيانات المياه الجوفية الحقيقية عبر Google Earth Engine

Primary Source — GLHYMPS v2.0 (Global Hydrogeology Maps):
    Global groundwater data at 30 arc-second (~1km) resolution.
    Hosted publicly in GEE at: users/ujjawal/GLHYMPS

    Key bands:
        - "depth"          : groundwater depth to water table (m below surface)
        - "T"              : transmissivity (m²/day)
        - "S"              : storativity (dimensionless, 0-1)
        - "recharge"       : recharge rate (mm/yr)
        - "type"           : aquifer type (categorical: 1-6)
        - "lithology"      : dominant lithology (categorical: 1-11)
        - "productivity"   : aquifer productivity (0-1)

Secondary Source — NASA/USGS GRACE-FO:
    For large-scale groundwater storage changes.
    Asset: NASA/GRACE/MASS_GRIDS/MASS_GRFO_CRI

Output of get_groundwater_data(lat, lon):
    {
        "success": True,
        "latitude": 30.0444,
        "longitude": 31.2357,
        "source": "gee",
        "depth_to_water_table_m": 15.3,
        "depth_label_ar": "ضحلة",
        "transmissivity_m2_day": 120.5,
        "transmissivity_label": "عالية",
        "storativity": 0.12,
        "recharge_mm_yr": 45.0,
        "aquifer_type_en": "Unconfined Sedimentary",
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.65,
        "productivity_label": "متوسطة-عالية",
        "dominant_lithology_en": "Sand and Gravel",
        "dominant_lithology_ar": "رمل وحصى",
        "water_quality_estimate": "جيدة",
        "trend_m_yr": -0.05,
        "data_quality": "high",
        "timestamp": "...",
    }
"""

import logging
from typing import Dict, Optional

from geological.gee_client import GEEClient

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# GLHYMPS GEE Asset
# ──────────────────────────────────────────────

GLHYMPS_ASSET = "users/ujjawal/GLHYMPS"

# Bands to query from GLHYMPS
GLHYMPS_BANDS = [
    "depth",        # depth to water table (m)
    "T",            # transmissivity (m²/day)
    "S",            # storativity
    "recharge",     # recharge rate (mm/yr)
    "type",         # aquifer type (categorical 1-6)
    "lithology",    # lithology (categorical 1-11)
    "productivity", # aquifer productivity (0-1)
]

# ── Aquifer Type Classification (GLHYMPS type codes) ──

AQUIFER_TYPES = {
    1: ("Unconfined Sedimentary", "رسوبي حر"),
    2: ("Confined Sedimentary", "رسوبي محبوس"),
    3: ("Unconsolidated Sedimentary", "رسوبي غير متماسك"),
    4: ("Consolidated Sedimentary", "رسوبي متماسك"),
    5: ("Crystalline/Bedrock", "صخري متبلور"),
    6: ("Volcanic", "بركاني"),
}

# ── Dominant Lithology (GLHYMPS lithology codes) ──

LITHOLOGY_MAP = {
    1:  ("Unconsolidated Sediments", "رواسب غير متماسكة"),
    2:  ("Sand and Gravel", "رمل وحصى"),
    3:  ("Sandstone", "حجر رملي"),
    4:  ("Carbonate Sedimentary", "رسوبي كربوناتي"),
    5:  ("Evaporite", "متبخرات"),
    6:  ("Metamorphic", "متغير"),
    7:  ("Igneous", "ناري"),
    8:  ("Volcanic", "بركاني"),
    9:  ("Weathered/Basement", "سطح متآكل"),
    10: ("Mixed Sedimentary", "رسوبي مختلط"),
    11: ("Complex/Unspecified", "مركب/غير محدد"),
}


def _depth_label(depth_m: float) -> str:
    """وصف عمق المياه الجوفية بالعربية"""
    if depth_m < 5:
        return "ضحلة جداً"
    elif depth_m < 15:
        return "ضحلة"
    elif depth_m < 30:
        return "متوسطة العمق"
    elif depth_m < 60:
        return "عميقة"
    else:
        return "عميقة جداً"


def _transmissivity_label(t_m2_day: float) -> str:
    """وصف نفاذية طبقة المياه"""
    if t_m2_day > 500:
        return "عالية جداً"
    elif t_m2_day > 100:
        return "عالية"
    elif t_m2_day > 10:
        return "متوسطة"
    elif t_m2_day > 1:
        return "منخفضة"
    else:
        return "منخفضة جداً"


def _productivity_label(prod: float) -> str:
    """وصف إنتاجية طبقة المياه الجوفية"""
    if prod > 0.7:
        return "عالية"
    elif prod > 0.4:
        return "متوسطة-عالية"
    elif prod > 0.2:
        return "متوسطة"
    elif prod > 0.05:
        return "منخفضة"
    else:
        return "منخفضة جداً"


def _estimate_water_quality(
    depth_m: Optional[float],
    recharge: Optional[float],
    lithology_code: Optional[int],
) -> str:
    """
    تقدير مبدئي لجودة المياه الجوفية

    في مصر، المياه الجوفية الضحلة في الدلتا ووادي النيل
    عادة ما تكون جيدة. المياه العميقة في الصحراء
    قد تكون مالحة.

    هذا تقدير تقريبي — يجب التحقق من تحاليل مخبرية.
    """
    if depth_m is None:
        return "غير محددة"

    # Northern Delta & coastal: shallow aquifers may have salinity
    # Desert regions: deep fossil aquifers can be brackish
    # Nile Valley: generally good quality

    score = 3  # neutral start

    if depth_m > 50:
        score -= 1  # deeper = potentially more saline (fossil water)
    if depth_m < 10:
        score -= 0.5  # very shallow = potential contamination risk

    if recharge is not None:
        if recharge > 100:
            score += 1  # high recharge = fresh water
        elif recharge < 10:
            score -= 1  # low recharge = potential salinity

    if lithology_code is not None:
        # Sand/gravel aquifers usually have better quality
        if lithology_code in (2, 3):
            score += 0.5
        # Evaporite = potential salinity
        if lithology_code == 5:
            score -= 2

    if score >= 3.5:
        return "جيدة جداً"
    elif score >= 2.5:
        return "جيدة"
    elif score >= 1.5:
        return "مقبولة"
    elif score >= 0.5:
        return "مشكوك فيها"
    else:
        return "سيئة (تحتاج تحليل مخبري)"


# ──────────────────────────────────────────────
# Groundwater Service
# ──────────────────────────────────────────────

class GroundwaterService:
    """
    خدمة بيانات المياه الجوفية — استخراج حقيقي عبر GEE

    Datasets:
        - GLHYMPS v2.0: depth, transmissivity, storativity, recharge,
                         aquifer type, lithology, productivity
        - NASA GRACE-FO: groundwater storage trends

    Usage:
        gw = GroundwaterService(gee_client)
        data = gw.get_groundwater_data(30.0444, 31.2357)
        print(data["depth_to_water_table_m"])  # 15.3
        print(data["aquifer_type_ar"])          # "رسوبي حر"
        print(data["water_quality_estimate"])   # "جيدة"
    """

    def __init__(self, gee_client: Optional[GEEClient] = None):
        self.gee = gee_client or GEEClient()
        if not self.gee.initialized:
            self.gee.initialize()

    def get_groundwater_data(
        self,
        lat: float,
        lon: float,
        scale: int = 1000,
    ) -> Dict[str, any]:
        """
        استخراج بيانات المياه الجوفية لنقطة محددة

        Args:
            lat: خط العرض
            lon: خط الطول
            scale: دقة الاستخراج بالمتر (1000m لـ GLHYMPS)

        Returns:
            قاموس بيانات المياه الجوفية
        """
        if not self.gee.is_ready():
            logger.warning("GEE not available — returning empty groundwater data")
            return self._empty_result(lat, lon, "gee_unavailable")

        # Query all bands in one call
        values = self.gee.get_pixel_value(
            image_asset=GLHYMPS_ASSET,
            bands=GLHYMPS_BANDS,
            lat=lat,
            lon=lon,
            scale=scale,
            reducer="first",
        )

        if not values:
            return self._empty_result(lat, lon, "no_data")

        from datetime import datetime, timezone

        # Extract values
        depth = values.get("depth")
        transmissivity = values.get("T")
        storativity = values.get("S")
        recharge = values.get("recharge")
        type_code = values.get("type")
        lith_code = values.get("lithology")
        productivity = values.get("productivity")

        # Decode categorical values
        aq_type_en, aq_type_ar = AQUIFER_TYPES.get(
            int(type_code), ("Unknown", "غير محدد")
        ) if type_code is not None else ("N/A", "غير متوفر")

        lith_en, lith_ar = LITHOLOGY_MAP.get(
            int(lith_code), ("Unknown", "غير محدد")
        ) if lith_code is not None else ("N/A", "غير متوفر")

        # Labels
        depth_label = _depth_label(depth) if depth is not None else "غير متوفر"
        t_label = _transmissivity_label(transmissivity) if transmissivity is not None else "غير متوفر"
        prod_label = _productivity_label(productivity) if productivity is not None else "غير متوفر"
        wq = _estimate_water_quality(depth, recharge, lith_code)

        # Data quality
        n_available = sum(1 for v in [depth, transmissivity, recharge] if v is not None)
        quality = "high" if n_available >= 3 else ("medium" if n_available >= 2 else "low")

        # Try to get GRACE trend (groundwater storage change)
        trend = self._get_grace_trend(lat, lon)

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "gee",
            "depth_to_water_table_m": round(depth, 2) if depth is not None else None,
            "depth_label_ar": depth_label,
            "transmissivity_m2_day": round(transmissivity, 2) if transmissivity is not None else None,
            "transmissivity_label": t_label,
            "storativity": round(storativity, 4) if storativity is not None else None,
            "recharge_mm_yr": round(recharge, 2) if recharge is not None else None,
            "aquifer_type_en": aq_type_en,
            "aquifer_type_ar": aq_type_ar,
            "aquifer_productivity": round(productivity, 4) if productivity is not None else None,
            "productivity_label": prod_label,
            "dominant_lithology_en": lith_en,
            "dominant_lithology_ar": lith_ar,
            "water_quality_estimate": wq,
            "trend_m_yr": trend,
            "data_quality": quality,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _get_grace_trend(self, lat: float, lon: float) -> Optional[float]:
        """
        استخراج اتجاه تغير مخزون المياه الجوفية من GRACE-FO

        Returns:
            تغير بالملليمتر/سنة (سلبي = تناقص)
        """
        grace_values = self.gee.get_time_series(
            collection_asset="NASA/GRACE/MASS_GRIDS/MASS_GRFO_CRI",
            bands=["lwe_thickness"],
            lat=lat,
            lon=lon,
            scale=50000,  # GRACE is ~150km resolution
            start_date="2018-06-01",
            end_date="2024-12-31",
        )

        if not grace_values or len(grace_values) < 2:
            return None

        # Simple linear trend
        lwe_values = [
            v.get("lwe_thickness", 0)
            for v in grace_values
            if isinstance(v.get("lwe_thickness"), (int, float))
        ]

        if len(lwe_values) < 2:
            return None

        n = len(lwe_values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(lwe_values) / n

        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(lwe_values))
        den = sum((i - x_mean) ** 2 for i in range(n))

        if den == 0:
            return None

        # Convert monthly slope to annual
        slope_monthly = num / den
        return round(slope_monthly * 12, 4)

    @staticmethod
    def _empty_result(lat: float, lon: float, reason: str) -> Dict[str, any]:
        """نتيجة فارغة"""
        return {
            "success": False,
            "latitude": lat,
            "longitude": lon,
            "source": "none",
            "reason": reason,
            "depth_to_water_table_m": None,
            "depth_label_ar": "غير متوفر",
            "transmissivity_m2_day": None,
            "transmissivity_label": "غير متوفر",
            "storativity": None,
            "recharge_mm_yr": None,
            "aquifer_type_en": "N/A",
            "aquifer_type_ar": "غير متوفر",
            "aquifer_productivity": None,
            "productivity_label": "غير متوفر",
            "dominant_lithology_en": "N/A",
            "dominant_lithology_ar": "غير متوفر",
            "water_quality_estimate": "غير محددة",
            "trend_m_yr": None,
            "data_quality": "none",
        }