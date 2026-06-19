"""
Soil Data Service
==================
استخراج بيانات التربة الحقيقية عبر Google Earth Engine

Primary Source — ISRIC Soil Grids v1 (250m resolution):
    These datasets are publicly hosted in GEE and provide
    global soil properties at 6 standard depths:
        0-5cm, 5-15cm, 15-30cm, 30-60cm, 60-100cm, 100-200cm

    Assets used (GEE ImageCollections):
        - Soil organic carbon content:   users/isricorg/soilgrids250m/soc_mean
        - Soil pH in H2O:                users/isricorg/soilgrids250m/phh2o_mean
        - Soil texture (sand/clay/silt): users/isricorg/soilgrids250m/{sand,clay,silt}_mean
        - Bulk density:                  users/isricorg/soilgrids250m/bdod_mean

Depth bands follow the naming convention:  "0-5cm", "5-15cm", "15-30cm", etc.
The standard reference depth for land evaluation is **0-30cm** (surface),
so we query the first 3 depth bands and average them.

Soil classification (USDA Triangle):
    Sand %, Clay %, Silt % → USDA soil texture class
    (12 major classes: Sand, Loamy Sand, Sandy Loam, Loam, Silt Loam, etc.)

Output of get_soil_data(lat, lon):
    {
        "success": True,
        "latitude": 30.0444,
        "longitude": 31.2357,
        "source": "gee",               # or "egsma" or "profile"
        "soil_type_ar": "طينية مزيجية",
        "soil_type_en": "Clay Loam",
        "usda_class": "Clay Loam",
        "ph": 8.2,
        "ph_label": "قلوية قليلاً",
        "organic_matter_pct": 1.2,
        "organic_carbon_g_kg": 6.9,
        "sand_pct": 30.0,
        "clay_pct": 40.0,
        "silt_pct": 30.0,
        "bulk_density_g_cm3": 1.35,
        "depth_cm": "0-30",
        "data_quality": "high",         # high / medium / low
        "timestamp": "...",
    }
"""

import logging
from typing import Dict, Optional, Tuple

from geological.gee_client import GEEClient

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# ISRIC Soil Grids — GEE Asset IDs
# ──────────────────────────────────────────────

# These are the actual public ISRIC Soil Grids v1 assets in GEE
# Each asset has bands named by depth: "0-5cm", "5-15cm", "15-30cm", ...
ISRIC_ASSETS = {
    "ph": "users/isricorg/soilgrids250m/phh2o_mean",
    "soc": "users/isricorg/soilgrids250m/soc_mean",         # g/kg (soil organic carbon)
    "sand": "users/isricorg/soilgrids250m/sand_mean",       # % (0-100)
    "clay": "users/isricorg/soilgrids250m/clay_mean",       # % (0-100)
    "silt": "users/isricorg/soilgrids250m/silt_mean",       # % (0-100)
    "bdod": "users/isricorg/soilgrids250m/bdod_mean",       # cg/cm³ (×10 to get g/cm³)
}

# Surface depth bands to average (0-30cm total)
SURFACE_DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]


# ──────────────────────────────────────────────
# USDA Soil Texture Classification
# ──────────────────────────────────────────────

# Simplified USDA triangle — based on %sand and %clay
# Full triangle has 12 classes; this covers the major ones
# found in Egypt's agricultural regions.

_USDA_CLASSES = [
    # (max_sand, max_clay, min_silt, class_en, class_ar, code)
    (100,  0,  0, "Sand",                    "رملية",                  "S"),
    ( 70, 15, 15, "Loamy Sand",              "رملية مزيجية",           "LS"),
    ( 52, 27,  7, "Sandy Loam",              "مزيجية رملية",           "SL"),
    ( 50, 20, 28, "Sandy Clay Loam",         "مزيجية طينية رملية",    "SCL"),
    ( 20, 55,  0, "Clay",                    "طينية",                  "C"),
    ( 35, 40, 15, "Silty Clay",              "طينية غرينية",           "SiC"),
    ( 15, 40, 40, "Silty Clay Loam",         "مزيجية طينية غرينية",   "SiCL"),
    ( 20, 27, 28, "Clay Loam",               "طينية مزيجية",           "CL"),
    ( 30, 17, 50, "Silt Loam",               "غرينية مزيجية",          "SiL"),
    (  0, 12, 80, "Silt",                    "غرينية",                 "Si"),
    ( 43, 18, 39, "Loam",                    "مزيجية",                 "L"),
    ( 45, 35, 20, "Sandy Clay",              "طينية رملية",            "SC"),
]


def classify_usda_texture(sand_pct: float, clay_pct: float, silt_pct: float) -> Tuple[str, str, str]:
    """
    تصنيف نسيج التربة وفق مثلث USDA

    Args:
        sand_pct: نسبة الرمل (0-100)
        clay_pct: نسبة الطين (0-100)
        silt_pct: نسبة الغرين (0-100)

    Returns:
        (usda_class_en, usda_class_ar, usda_code)
    """
    best = ("Loam", "مزيجية", "L")
    best_diff = 999.0

    for (max_sand, max_clay, min_silt, en, ar, code) in _USDA_CLASSES:
        # Simple distance-based matching
        diff = (
            abs(sand_pct - max_sand) * 0.5 +
            abs(clay_pct - max_clay) * 0.5 +
            abs(silt_pct - (100 - max_sand - max_clay)) * 0.3
        )
        if diff < best_diff:
            best_diff = diff
            best = (en, ar, code)

    return best


def ph_label_ar(ph: float) -> str:
    """وصف درجة pH بالعربية"""
    if ph < 4.5:
        return "شديدة الحموضة"
    elif ph < 5.5:
        return "حمضية"
    elif ph < 6.5:
        return "حمضية قليلاً"
    elif ph < 7.3:
        return "محايدة"
    elif ph < 7.8:
        return "قلوية قليلاً"
    elif ph < 8.5:
        return "قلوية"
    else:
        return "شديدة القلوية"


def organic_carbon_to_matter(soc_g_kg: float) -> float:
    """
    تحويل المادة العضوية الكربونية (g/kg) إلى نسبة مادة عضوية (%)
    Using Van Bemmelen factor: OM% = SOC(g/kg) × 0.1 × 1.724

    The factor 1.724 is the standard ratio (OM = 58% C by weight).
    """
    return round(soc_g_kg * 0.1 * 1.724, 2)


# ──────────────────────────────────────────────
# Soil Service
# ──────────────────────────────────────────────

class SoilService:
    """
    خدمة بيانات التربة — استخراج حقيقي عبر GEE

    GEE datasets (ISRIC Soil Grids v1, 250m):
        - pH (H2O)         → 0-14 scale
        - SOC              → g/kg organic carbon
        - Sand / Clay / Silt → percentages
        - Bulk Density     → cg/cm³

    Usage:
        soil = SoilService(gee_client)
        data = soil.get_soil_data(30.0444, 31.2357)
        print(data["soil_type_ar"])  # "طينية مزيجية"
        print(data["ph"])             # 8.2
        print(data["organic_matter_pct"])  # 1.2
    """

    def __init__(self, gee_client: Optional[GEEClient] = None):
        """
        Args:
            gee_client: عميل GEE (اختياري — يُنشأ تلقائياً)
        """
        self.gee = gee_client or GEEClient()

        # Try to initialize GEE
        if not self.gee.initialized:
            self.gee.initialize()

    def get_soil_data(
        self,
        lat: float,
        lon: float,
        scale: int = 250,
    ) -> Dict[str, any]:
        """
        استخراج بيانات التربة لنقطة محددة

        Args:
            lat: خط العرض
            lon: خط الطول
            scale: دقة الاستخراج بالمتر (250m لـ Soil Grids)

        Returns:
            قاموس بيانات التربة (انظر وصف Output في أعلى الملف)
        """
        if not self.gee.is_ready():
            logger.warning("GEE not available — returning empty soil data")
            return self._empty_result(lat, lon, "gee_unavailable")

        # ── Step 1: Query pH ──
        ph_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["ph"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )

        # ── Step 2: Query SOC (Soil Organic Carbon) ──
        soc_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["soc"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )

        # ── Step 3: Query Sand, Clay, Silt ──
        sand_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["sand"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )
        clay_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["clay"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )
        silt_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["silt"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )

        # ── Step 4: Query Bulk Density ──
        bdod_values = self._query_depth_averaged(
            asset=ISRIC_ASSETS["bdod"],
            lat=lat, lon=lon, scale=scale,
            depths=SURFACE_DEPTHS,
        )

        # ── Step 5: Validate and build result ──
        if ph_values is None and soc_values is None:
            return self._empty_result(lat, lon, "no_data")

        from datetime import datetime, timezone

        ph = ph_values if ph_values is not None else None
        soc = soc_values if soc_values is not None else 0.0
        sand = sand_values if sand_values is not None else 33.3
        clay = clay_values if clay_values is not None else 33.3
        silt = silt_values if silt_values is not None else 33.4

        # Ensure sum ≈ 100
        total = sand + clay + silt
        if total > 0:
            sand = round(sand / total * 100, 1)
            clay = round(clay / total * 100, 1)
            silt = round(silt / total * 100, 1)

        # Bulk density: ISRIC stores in cg/cm³, convert to g/cm³
        bd = bdod_values / 10.0 if bdod_values is not None else None

        # Organic matter %
        om_pct = organic_carbon_to_matter(soc)

        # USDA classification
        usda_en, usda_ar, usda_code = classify_usda_texture(sand, clay, silt)

        # Determine data quality
        n_available = sum(1 for v in [ph_values, soc_values, sand_values] if v is not None)
        quality = "high" if n_available >= 3 else ("medium" if n_available >= 2 else "low")

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "gee",
            "soil_type_ar": usda_ar,
            "soil_type_en": usda_en,
            "usda_class": f"{usda_en} ({usda_code})",
            "ph": ph,
            "ph_label": ph_label_ar(ph) if ph is not None else "غير متوفر",
            "organic_matter_pct": om_pct,
            "organic_carbon_g_kg": round(soc, 2) if soc else 0.0,
            "sand_pct": sand,
            "clay_pct": clay,
            "silt_pct": silt,
            "bulk_density_g_cm3": round(bd, 2) if bd is not None else None,
            "depth_cm": "0-30",
            "data_quality": quality,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────
    # Internal: Depth-Averaged Query
    # ──────────────────────────────────────────

    def _query_depth_averaged(
        self,
        asset: str,
        lat: float,
        lon: float,
        scale: int,
        depths: list,
    ) -> Optional[float]:
        """
        استعلام نطاقات عمق متعددة وحساب المتوسط

        ISRIC Soil Grids stores each depth as a separate band.
        We query all surface depths and average the valid values.
        """
        values = self.gee.get_pixel_value(
            image_asset=asset,
            bands=depths,
            lat=lat,
            lon=lon,
            scale=scale,
            reducer="first",
        )

        if not values:
            return None

        # Collect valid numeric values
        valid = []
        for depth, val in values.items():
            if isinstance(val, (int, float)) and val >= 0:
                valid.append(float(val))

        if not valid:
            return None

        return round(sum(valid) / len(valid), 2)

    @staticmethod
    def _empty_result(lat: float, lon: float, reason: str) -> Dict[str, any]:
        """نتيجة فارغة عند عدم توفر البيانات"""
        return {
            "success": False,
            "latitude": lat,
            "longitude": lon,
            "source": "none",
            "reason": reason,
            "soil_type_ar": "غير متوفر",
            "soil_type_en": "N/A",
            "usda_class": "N/A",
            "ph": None,
            "ph_label": "غير متوفر",
            "organic_matter_pct": None,
            "organic_carbon_g_kg": None,
            "sand_pct": None,
            "clay_pct": None,
            "silt_pct": None,
            "bulk_density_g_cm3": None,
            "depth_cm": "0-30",
            "data_quality": "none",
        }