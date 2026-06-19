"""
Geological Service — Main Orchestrator
=========================================
المُنسق المركزي لخدمة البيانات الجيولوجية

Data Resolution Strategy (ordered by priority):
    1. Google Earth Engine (real-time, global, free)
       → ISRIC Soil Grids + GLHYMPS + GRACE-FO
    2. EGSMA GeoTIFF (local files, Egypt-specific, high detail)
       → Requires .tif files from EGSMA
    3. Egypt Soil Profiles (in-memory, based on published FAO/EGSMA surveys)
       → Always available as final fallback

Public API:
    geological = GeologicalService()
    soil = geological.get_soil_data(30.0444, 31.2357)
    gw   = geological.get_groundwater_data(30.0444, 31.2357)
    full = geological.get_full_profile(30.0444, 31.2357)
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any, Tuple

from geological.gee_client import GEEClient
from geological.soil_service import SoilService, classify_usda_texture, ph_label_ar, organic_carbon_to_matter
from geological.groundwater_service import GroundwaterService, _depth_label, _estimate_water_quality
from geological.egsma_reader import EGSMAReader, EGSMA_SOIL_LEGEND

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Egypt Soil Profile Database
# ──────────────────────────────────────────────
# Based on published data from:
#   - FAO Soil Map of the World (Harmonized)
#   - EGSMA (Egyptian Geological Survey and Mining Authority)
#   - Agricultural Research Center (ARC), Egypt
#   - FAO AQUASTAT Egypt country profile
#   - "Soils of Egypt" — Abdel-Kader (2012)
#
# These profiles represent MAJOR SOIL ZONES.
# Individual points within each zone may vary.

# Each profile covers an approximate lat/lon box.
# When GEE and EGSMA are unavailable, we use nearest-neighbor
# matching to find the closest profile.

_EGYPT_SOIL_PROFILES: List[Dict[str, Any]] = [
    # ── Nile Delta ──
    {
        "region": "الدلتا — شمال",
        "region_en": "Nile Delta — North",
        "center": (30.8, 31.0),
        "box": [(30.0, 29.5), (31.5, 32.0)],  # (lat_min, lon_min), (lat_max, lon_max)
        "soil_type_ar": "طينية مزيجية",
        "soil_type_en": "Clay Loam",
        "usda_class": "Clay Loam",
        "ph": 7.8,
        "organic_matter_pct": 1.8,
        "sand_pct": 28.0,
        "clay_pct": 42.0,
        "silt_pct": 30.0,
        "bulk_density_g_cm3": 1.30,
        "groundwater_depth_m": 1.5,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.85,
        "recharge_mm_yr": 120.0,
        "water_quality": "جيدة",
        "lithology_ar": "رمل وحصى",
        "suitability": "ممتاز",
        "notes": "تربة طينية خصبة من رواسب النيل — منطقة زراعية كثيفة",
    },
    {
        "region": "الدلتا — وسط",
        "region_en": "Nile Delta — Central",
        "center": (30.5, 31.2),
        "box": [(30.0, 30.5), (31.0, 32.0)],
        "soil_type_ar": "طينية",
        "soil_type_en": "Clay",
        "usda_class": "Clay",
        "ph": 7.9,
        "organic_matter_pct": 2.1,
        "sand_pct": 20.0,
        "clay_pct": 55.0,
        "silt_pct": 25.0,
        "bulk_density_g_cm3": 1.25,
        "groundwater_depth_m": 2.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.80,
        "recharge_mm_yr": 100.0,
        "water_quality": "جيدة",
        "lithology_ar": "رمل وحصى",
        "suitability": "ممتاز",
        "notes": "طين النيل الخصب — أعلى إنتاجية زراعية في مصر",
    },
    {
        "region": "الدلتا — شرق",
        "region_en": "Nile Delta — East",
        "center": (30.9, 31.8),
        "box": [(30.5, 31.5), (31.3, 32.5)],
        "soil_type_ar": "مزيجية طينية رملية",
        "soil_type_en": "Sandy Clay Loam",
        "usda_class": "Sandy Clay Loam",
        "ph": 8.0,
        "organic_matter_pct": 1.5,
        "sand_pct": 42.0,
        "clay_pct": 33.0,
        "silt_pct": 25.0,
        "bulk_density_g_cm3": 1.35,
        "groundwater_depth_m": 3.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.70,
        "recharge_mm_yr": 80.0,
        "water_quality": "جيدة",
        "lithology_ar": "رمل وحصى",
        "suitability": "جيد جداً",
        "notes": "منطقة انتقالية بين الدلتا والصحراء الشرقية",
    },
    # ── Cairo / Greater Cairo ──
    {
        "region": "القاهرة الكبرى",
        "region_en": "Greater Cairo",
        "center": (30.05, 31.25),
        "box": [(29.8, 31.0), (30.3, 31.6)],
        "soil_type_ar": "مزيجية رملية",
        "soil_type_en": "Sandy Loam",
        "usda_class": "Sandy Loam",
        "ph": 8.3,
        "organic_matter_pct": 0.8,
        "sand_pct": 55.0,
        "clay_pct": 20.0,
        "silt_pct": 25.0,
        "bulk_density_g_cm3": 1.45,
        "groundwater_depth_m": 5.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.60,
        "recharge_mm_yr": 40.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رسوبي مختلط",
        "suitability": "متوسط",
        "notes": "تربة حضرية — ضغط سكاني عالي وتبلور ملحي في بعض المناطق",
    },
    # ── Nile Valley (Upper Egypt) ──
    {
        "region": "وادي النيل — صعيد",
        "region_en": "Nile Valley — Upper Egypt",
        "center": (26.5, 32.5),
        "box": [(24.0, 32.0), (29.0, 33.5)],
        "soil_type_ar": "مزيجية رملية",
        "soil_type_en": "Sandy Loam",
        "usda_class": "Sandy Loam",
        "ph": 8.1,
        "organic_matter_pct": 1.0,
        "sand_pct": 50.0,
        "clay_pct": 22.0,
        "silt_pct": 28.0,
        "bulk_density_g_cm3": 1.42,
        "groundwater_depth_m": 8.0,
        "aquifer_type_ar": "رسوبي محبوس",
        "aquifer_productivity": 0.45,
        "recharge_mm_yr": 25.0,
        "water_quality": "جيدة",
        "lithology_ar": "رسوبي مختلط",
        "suitability": "جيد",
        "notes": "وادي النيل الضيق — تربة رملية مزيجية مع طبقة طينية",
    },
    # ── Western Desert Oases ──
    {
        "region": "الواحات — الصحراء الغربية",
        "region_en": "Western Desert Oases",
        "center": (27.0, 28.5),
        "box": [(24.0, 25.0), (30.0, 30.0)],
        "soil_type_ar": "رملية",
        "soil_type_en": "Sand",
        "usda_class": "Sand",
        "ph": 8.5,
        "organic_matter_pct": 0.2,
        "sand_pct": 90.0,
        "clay_pct": 3.0,
        "silt_pct": 7.0,
        "bulk_density_g_cm3": 1.60,
        "groundwater_depth_m": 25.0,
        "aquifer_type_ar": "رسوبي محبوس (NUBIAN)",
        "aquifer_productivity": 0.55,
        "recharge_mm_yr": 5.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رمل وحصى",
        "suitability": "محدود",
        "notes": "كثبان رملية — مياه جوفية عميقة من تكوين النوبي الحجري",
    },
    # ── Eastern Desert ──
    {
        "region": "الصحراء الشرقية",
        "region_en": "Eastern Desert",
        "center": (27.0, 33.0),
        "box": [(24.0, 33.0), (30.0, 36.0)],
        "soil_type_ar": "حجرية رملية",
        "soil_type_en": "Rocky Sandy",
        "usda_class": "Loamy Sand",
        "ph": 8.7,
        "organic_matter_pct": 0.1,
        "sand_pct": 75.0,
        "clay_pct": 8.0,
        "silt_pct": 17.0,
        "bulk_density_g_cm3": 1.55,
        "groundwater_depth_m": 40.0,
        "aquifer_type_ar": "صخري متبلور",
        "aquifer_productivity": 0.15,
        "recharge_mm_yr": 3.0,
        "water_quality": "مشكوك فيها",
        "lithology_ar": "صخري متبلور",
        "suitability": "غير مناسب",
        "notes": "صخور نارية ومتحولة — مياه جوفية محدودة جداً",
    },
    # ── Suez Canal Zone ──
    {
        "region": "منطقة قناة السويس",
        "region_en": "Suez Canal Zone",
        "center": (30.3, 32.3),
        "box": [(29.5, 31.8), (31.0, 32.8)],
        "soil_type_ar": "رملية مزيجية",
        "soil_type_en": "Loamy Sand",
        "usda_class": "Loamy Sand",
        "ph": 8.2,
        "organic_matter_pct": 0.5,
        "sand_pct": 68.0,
        "clay_pct": 12.0,
        "silt_pct": 20.0,
        "bulk_density_g_cm3": 1.50,
        "groundwater_depth_m": 4.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.50,
        "recharge_mm_yr": 30.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رسوبي مختلط",
        "suitability": "متوسط",
        "notes": "منطقة صناعية — تربة رملية مع ملوحة متوسطة",
    },
    # ── North Coast / Mediterranean ──
    {
        "region": "الساحل الشمالي",
        "region_en": "North Coast",
        "center": (30.9, 28.9),
        "box": [(30.5, 25.0), (31.5, 30.5)],
        "soil_type_ar": "رملية كثيفة",
        "soil_type_en": "Sand Dunes",
        "usda_class": "Sand",
        "ph": 8.0,
        "organic_matter_pct": 0.3,
        "sand_pct": 92.0,
        "clay_pct": 3.0,
        "silt_pct": 5.0,
        "bulk_density_g_cm3": 1.58,
        "groundwater_depth_m": 3.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.40,
        "recharge_mm_yr": 60.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رمل وحصى",
        "suitability": "محدود",
        "notes": "كثبان رملية ساحلية — ملوحة مرتفعة بالقرب من البحر",
    },
    # ── New Valley / Toshka ──
    {
        "region": "الوادي الجديد / توشكى",
        "region_en": "New Valley / Toshka",
        "center": (22.9, 31.5),
        "box": [(22.0, 30.0), (24.0, 33.0)],
        "soil_type_ar": "ريج صحراوي",
        "soil_type_en": "Desert Soil",
        "usda_class": "Sandy Loam",
        "ph": 8.8,
        "organic_matter_pct": 0.15,
        "sand_pct": 65.0,
        "clay_pct": 15.0,
        "silt_pct": 20.0,
        "bulk_density_g_cm3": 1.52,
        "groundwater_depth_m": 30.0,
        "aquifer_type_ar": "رسوبي محبوس (NUBIAN)",
        "aquifer_productivity": 0.50,
        "recharge_mm_yr": 2.0,
        "water_quality": "مشكوك فيها",
        "lithology_ar": "رمل وحصى",
        "suitability": "محدود",
        "notes": "صحراء مطلقة — مشروع توشكى يستخدم مياه النيل المنقولة",
    },
    # ── Sinai ──
    {
        "region": "شبه جزيرة سيناء",
        "region_en": "Sinai Peninsula",
        "center": (29.5, 33.5),
        "box": [(27.5, 32.0), (31.5, 35.0)],
        "soil_type_ar": "حجرية رملية",
        "soil_type_en": "Rocky Sandy",
        "usda_class": "Loamy Sand",
        "ph": 8.4,
        "organic_matter_pct": 0.2,
        "sand_pct": 72.0,
        "clay_pct": 10.0,
        "silt_pct": 18.0,
        "bulk_density_g_cm3": 1.50,
        "groundwater_depth_m": 35.0,
        "aquifer_type_ar": "صخري متبلور",
        "aquifer_productivity": 0.20,
        "recharge_mm_yr": 5.0,
        "water_quality": "متوسطة",
        "lithology_ar": "صخري متبلور",
        "suitability": "محدود",
        "notes": "تضاريس جبلية وصحراوية — وادي فيران استثناء خصب",
    },
    # ── Fayoum Depression ──
    {
        "region": "الفيوم",
        "region_en": "Fayoum",
        "center": (29.3, 30.8),
        "box": [(29.0, 30.3), (29.7, 31.2)],
        "soil_type_ar": "طينية مزيجية",
        "soil_type_en": "Clay Loam",
        "usda_class": "Clay Loam",
        "ph": 8.1,
        "organic_matter_pct": 1.4,
        "sand_pct": 30.0,
        "clay_pct": 38.0,
        "silt_pct": 32.0,
        "bulk_density_g_cm3": 1.35,
        "groundwater_depth_m": 3.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.70,
        "recharge_mm_yr": 50.0,
        "water_quality": "جيدة",
        "lithology_ar": "رمل وحصى",
        "suitability": "جيد جداً",
        "notes": "منخفض الفيوم — تربة خصبة ومياه من بحيرة قارون",
    },
    # ── New Administrative Capital area ──
    {
        "region": "المنطقة الشرقية الجديدة",
        "region_en": "New Administrative Capital Area",
        "center": (30.05, 31.85),
        "box": [(29.7, 31.5), (30.4, 32.2)],
        "soil_type_ar": "مزيجية رملية",
        "soil_type_en": "Sandy Loam",
        "usda_class": "Sandy Loam",
        "ph": 8.4,
        "organic_matter_pct": 0.5,
        "sand_pct": 58.0,
        "clay_pct": 18.0,
        "silt_pct": 24.0,
        "bulk_density_g_cm3": 1.48,
        "groundwater_depth_m": 12.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.45,
        "recharge_mm_yr": 15.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رسوبي مختلط",
        "suitability": "متوسط",
        "notes": "صحراء تم تطويرها — بنية تحتية جديدة، تحتاج تحسين التربة",
    },
    # ── Alexandria ──
    {
        "region": "الإسكندرية",
        "region_en": "Alexandria",
        "center": (31.2, 29.9),
        "box": [(30.8, 29.5), (31.4, 30.3)],
        "soil_type_ar": "رملية مزيجية",
        "soil_type_en": "Loamy Sand",
        "usda_class": "Loamy Sand",
        "ph": 8.0,
        "organic_matter_pct": 0.7,
        "sand_pct": 65.0,
        "clay_pct": 12.0,
        "silt_pct": 23.0,
        "bulk_density_g_cm3": 1.50,
        "groundwater_depth_m": 2.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.65,
        "recharge_mm_yr": 90.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رمل وحصى",
        "suitability": "متوسط",
        "notes": "منطقة ساحلية — ملوحة متزايدة بسبب ارتفاع منسوب البحر",
    },
    # ── 6th October / West Cairo ──
    {
        "region": "المنطقة الغربية — 6 أكتوبر",
        "region_en": "6th October / West Cairo",
        "center": (29.95, 31.0),
        "box": [(29.5, 30.5), (30.2, 31.3)],
        "soil_type_ar": "لوحية رملية",
        "soil_type_en": "Calcareous Sandy Loam",
        "usda_class": "Sandy Loam",
        "ph": 8.6,
        "organic_matter_pct": 0.4,
        "sand_pct": 62.0,
        "clay_pct": 15.0,
        "silt_pct": 23.0,
        "bulk_density_g_cm3": 1.50,
        "groundwater_depth_m": 10.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.40,
        "recharge_mm_yr": 20.0,
        "water_quality": "مقبولة",
        "lithology_ar": "رسوبي كربوناتي",
        "suitability": "متوسط",
        "notes": "صحراء كربوناتية — تكلس مرتفع في التربة",
    },
    # ── Port Said / Damietta ──
    {
        "region": "بورسعيد ودمياط",
        "region_en": "Port Said / Damietta",
        "center": (31.3, 31.8),
        "box": [(31.0, 31.2), (31.6, 32.3)],
        "soil_type_ar": "طينية",
        "soil_type_en": "Clay",
        "usda_class": "Clay",
        "ph": 7.7,
        "organic_matter_pct": 2.0,
        "sand_pct": 18.0,
        "clay_pct": 52.0,
        "silt_pct": 30.0,
        "bulk_density_g_cm3": 1.28,
        "groundwater_depth_m": 1.0,
        "aquifer_type_ar": "رسوبي حر",
        "aquifer_productivity": 0.90,
        "recharge_mm_yr": 150.0,
        "water_quality": "جيدة جداً",
        "lithology_ar": "رمل وحصى",
        "suitability": "ممتاز",
        "notes": "أرض الدلتا الشمالية — أكثر المناطق خصوبة مع ارتفاع منسوب المياه",
    },
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """حساب المسافة بين نقطتين بالكيلومتر"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _find_nearest_profile(lat: float, lon: float) -> Tuple[Dict[str, Any], float]:
    """
    إيجاد أقرب ملف تربة من قاعدة البيانات

    Uses haversine distance to find the nearest soil zone center.
    """
    best_profile = _EGYPT_SOIL_PROFILES[0]
    best_dist = 9999.0

    for profile in _EGYPT_SOIL_PROFILES:
        clat, clon = profile["center"]
        dist = _haversine_km(lat, lon, clat, clon)
        if dist < best_dist:
            best_dist = dist
            best_profile = profile

    return best_profile, best_dist


# ──────────────────────────────────────────────
# Geological Service — Main
# ──────────────────────────────────────────────

class GeologicalService:
    """
    خدمة البيانات الجيولوجية — الواجهة الرئيسية

    Data Sources (tried in order):
        1. GEE (ISRIC + GLHYMPS)   → real satellite data, free
        2. EGSMA GeoTIFF (rasterio) → local high-detail Egypt maps
        3. Egypt Profiles (in-memory)→ published survey data, always available

    Usage:
        geo = GeologicalService()

        # Soil data
        soil = geo.get_soil_data(30.0444, 31.2357)
        print(soil["soil_type_ar"])        # "مزيجية رملية"
        print(soil["ph"])                   # 8.3
        print(soil["organic_matter_pct"])   # 0.8

        # Groundwater data
        gw = geo.get_groundwater_data(30.0444, 31.2357)
        print(gw["depth_to_water_table_m"])  # 5.0
        print(gw["aquifer_type_ar"])          # "رسوبي حر"

        # Full profile
        full = geo.get_full_profile(30.0444, 31.2357)
        print(full["soil"]["soil_type_ar"])
        print(full["groundwater"]["aquifer_type_ar"])
    """

    def __init__(
        self,
        gee_client: Optional[GEEClient] = None,
        egsma_data_dir: str = "",
    ):
        """
        Args:
            gee_client: عميل GEE (اختياري — يُنشأ تلقائياً)
            egsma_data_dir: مسار ملفات EGSMA GeoTIFF
        """
        # Initialize GEE
        self.gee = gee_client or GEEClient()
        if not self.gee.initialized:
            self.gee.initialize()
        self.gee_available = self.gee.is_ready()

        # Initialize EGSMA reader
        self.egsma = EGSMAReader(data_dir=egsma_data_dir)
        self.egsma_available = len(self.egsma._available_layers) > 0

        # Initialize sub-services
        self.soil_service = SoilService(self.gee)
        self.gw_service = GroundwaterService(self.gee)

        # Profile fallback distance threshold (km)
        self.profile_max_distance = 200.0

        logger.info(
            f"GeologicalService initialized | "
            f"GEE={self.gee_available} | "
            f"EGSMA={self.egsma_available} | "
            f"profiles={len(_EGYPT_SOIL_PROFILES)}"
        )

    # ──────────────────────────────────────────
    # Public API: Soil
    # ──────────────────────────────────────────

    def get_soil_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        استخراج بيانات التربة — الدالة الرئيسية

        Resolution strategy:
            1. GEE (ISRIC Soil Grids v1, 250m) → real data
            2. EGSMA GeoTIFF (local)             → Egypt-specific
            3. Egypt profiles (in-memory)        → always available

        Args:
            lat: خط العرض
            lon: خط الطول

        Returns:
            {
                "success": True,
                "soil_type_ar": "مزيجية رملية",
                "soil_type_en": "Sandy Loam",
                "ph": 8.3,
                "ph_label": "قلوية قليلاً",
                "organic_matter_pct": 0.8,
                "sand_pct": 55.0,
                "clay_pct": 20.0,
                "silt_pct": 25.0,
                "source": "profile",
                "data_quality": "medium",
                ...
            }
        """
        # ── Try GEE first ──
        if self.gee_available:
            gee_result = self.soil_service.get_soil_data(lat, lon)
            if gee_result.get("success"):
                gee_result["fallback_used"] = False
                return gee_result

        # ── Try EGSMA ──
        if self.egsma_available:
            egsma_result = self._get_soil_from_egsma(lat, lon)
            if egsma_result.get("success"):
                return egsma_result

        # ── Fallback: Egypt profiles ──
        return self._get_soil_from_profile(lat, lon)

    # ──────────────────────────────────────────
    # Public API: Groundwater
    # ──────────────────────────────────────────

    def get_groundwater_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        استخراج بيانات المياه الجوفية — الدالة الرئيسية

        Resolution strategy:
            1. GEE (GLHYMPS v2.0, ~1km) → real data
            2. EGSMA GeoTIFF (local)        → Egypt-specific
            3. Egypt profiles (in-memory)   → always available

        Args:
            lat: خط العرض
            lon: خط الطول

        Returns:
            {
                "success": True,
                "depth_to_water_table_m": 5.0,
                "depth_label_ar": "ضحلة",
                "aquifer_type_ar": "رسوبي حر",
                "water_quality_estimate": "مقبولة",
                ...
            }
        """
        # ── Try GEE first ──
        if self.gee_available:
            gee_result = self.gw_service.get_groundwater_data(lat, lon)
            if gee_result.get("success"):
                gee_result["fallback_used"] = False
                return gee_result

        # ── Try EGSMA ──
        if self.egsma_available:
            egsma_result = self._get_gw_from_egsma(lat, lon)
            if egsma_result.get("success"):
                return egsma_result

        # ── Fallback: Egypt profiles ──
        return self._get_gw_from_profile(lat, lon)

    # ──────────────────────────────────────────
    # Public API: Full Profile
    # ──────────────────────────────────────────

    def get_full_profile(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        استخراج الملف الجيولوجي الكامل (تربة + مياه جوفية)

        Returns:
            {
                "latitude": 30.0444,
                "longitude": 31.2357,
                "soil": {...},
                "groundwater": {...},
                "source_summary": "profile",
                "suitability_score": 7,
                "timestamp": "...",
            }
        """
        soil = self.get_soil_data(lat, lon)
        gw = self.get_groundwater_data(lat, lon)

        # Determine overall source
        sources = set()
        if soil.get("source"):
            sources.add(soil["source"])
        if gw.get("source"):
            sources.add(gw["source"])

        if "gee" in sources:
            source_summary = "gee"
        elif "egsma" in sources:
            source_summary = "egsma"
        else:
            source_summary = "profile"

        # Suitability score (1-10)
        suitability = self._compute_suitability(soil, gw)

        return {
            "latitude": lat,
            "longitude": lon,
            "soil": soil,
            "groundwater": gw,
            "source_summary": source_summary,
            "suitability_score": suitability,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────
    # EGSMA Fallback
    # ──────────────────────────────────────────

    def _get_soil_from_egsma(self, lat: float, lon: float) -> Dict[str, Any]:
        """استخراج بيانات التربة من ملفات EGSMA"""
        # Try to read soil type (categorical)
        soil_type = self.egsma.read_categorical(
            "soil_type_egypt", lat, lon,
            legend=EGSMA_SOIL_LEGEND,
        )

        # Try to read pH (continuous)
        ph_val = self.egsma.read_point("ph_egypt", lat, lon)

        # Try to read organic matter (continuous)
        om_val = self.egsma.read_point("organic_matter_egypt", lat, lon)

        has_data = (soil_type is not None or ph_val is not None or om_val is not None)
        if not has_data:
            return {"success": False, "source": "egsma"}

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "egsma",
            "soil_type_ar": soil_type["label_ar"] if soil_type else "غير متوفر",
            "soil_type_en": soil_type["label_en"] if soil_type else "N/A",
            "usda_class": soil_type["label_en"] if soil_type else "N/A",
            "ph": ph_val,
            "ph_label": ph_label_ar(ph_val) if ph_val else "غير متوفر",
            "organic_matter_pct": om_val,
            "sand_pct": None,
            "clay_pct": None,
            "silt_pct": None,
            "bulk_density_g_cm3": None,
            "depth_cm": "0-30",
            "data_quality": "high" if soil_type else "medium",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _get_gw_from_egsma(self, lat: float, lon: float) -> Dict[str, Any]:
        """استخراج بيانات المياه من ملفات EGSMA"""
        depth_val = self.egsma.read_point("groundwater_depth_egypt", lat, lon)

        if depth_val is None:
            return {"success": False, "source": "egsma"}

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "egsma",
            "depth_to_water_table_m": depth_val,
            "depth_label_ar": _depth_label(depth_val),
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
            "water_quality_estimate": _estimate_water_quality(depth_val, None, None),
            "trend_m_yr": None,
            "data_quality": "medium",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────
    # Egypt Profile Fallback
    # ──────────────────────────────────────────

    def _get_soil_from_profile(self, lat: float, lon: float) -> Dict[str, Any]:
        """استخراج بيانات التربة من ملفات مصر المرجعية"""
        profile, dist = _find_nearest_profile(lat, lon)

        quality = "high" if dist < 30 else ("medium" if dist < 80 else "low")

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "profile",
            "source_region": profile["region"],
            "distance_to_profile_km": round(dist, 1),
            "soil_type_ar": profile["soil_type_ar"],
            "soil_type_en": profile["soil_type_en"],
            "usda_class": profile["usda_class"],
            "ph": profile["ph"],
            "ph_label": ph_label_ar(profile["ph"]),
            "organic_matter_pct": profile["organic_matter_pct"],
            "organic_carbon_g_kg": round(profile["organic_matter_pct"] / 1.724 / 0.1, 2),
            "sand_pct": profile["sand_pct"],
            "clay_pct": profile["clay_pct"],
            "silt_pct": profile["silt_pct"],
            "bulk_density_g_cm3": profile["bulk_density_g_cm3"],
            "depth_cm": "0-30",
            "data_quality": quality,
            "notes": profile.get("notes", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _get_gw_from_profile(self, lat: float, lon: float) -> Dict[str, Any]:
        """استخراج بيانات المياه من ملفات مصر المرجعية"""
        profile, dist = _find_nearest_profile(lat, lon)

        quality = "high" if dist < 30 else ("medium" if dist < 80 else "low")

        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "source": "profile",
            "source_region": profile["region"],
            "distance_to_profile_km": round(dist, 1),
            "depth_to_water_table_m": profile["groundwater_depth_m"],
            "depth_label_ar": _depth_label(profile["groundwater_depth_m"]),
            "transmissivity_m2_day": None,
            "transmissivity_label": "غير متوفر",
            "storativity": None,
            "recharge_mm_yr": profile.get("recharge_mm_yr"),
            "aquifer_type_en": profile["aquifer_type_ar"],
            "aquifer_type_ar": profile["aquifer_type_ar"],
            "aquifer_productivity": profile["aquifer_productivity"],
            "productivity_label": (
                "عالية" if profile["aquifer_productivity"] > 0.7
                else "متوسطة" if profile["aquifer_productivity"] > 0.4
                else "منخفضة"
            ),
            "dominant_lithology_en": profile.get("lithology_ar", "N/A"),
            "dominant_lithology_ar": profile.get("lithology_ar", "غير متوفر"),
            "water_quality_estimate": profile.get("water_quality", "غير محددة"),
            "trend_m_yr": None,
            "data_quality": quality,
            "notes": profile.get("notes", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────
    # Suitability Scoring
    # ──────────────────────────────────────────

    @staticmethod
    def _compute_suitability(soil: Dict, gw: Dict) -> int:
        """
        حساب درجة ملاءمة الأرض للاستثمار (1-10)

        Criteria:
            - Organic matter (0-3 pts): high OM = fertile
            - pH balance (0-2 pts): 6.5-7.5 ideal
            - Soil texture (0-2 pts): loam/clay loam ideal
            - Groundwater depth (0-2 pts): 1-10m ideal
            - Water quality (0-1 pt): good/very good
        """
        score = 5  # base

        # Organic matter (0-3)
        om = soil.get("organic_matter_pct")
        if om is not None:
            if om >= 2.0:
                score += 3
            elif om >= 1.0:
                score += 2
            elif om >= 0.5:
                score += 1

        # pH balance (0-2)
        ph = soil.get("ph")
        if ph is not None:
            if 6.5 <= ph <= 7.5:
                score += 2
            elif 7.5 < ph <= 8.5:
                score += 1

        # Texture (0-2)
        usda = soil.get("usda_class", "")
        if "Loam" in usda and "Sand" not in usda:
            score += 2
        elif "Sandy" in usda or "Sand" == usda:
            score += 0
        else:
            score += 1

        # Groundwater depth (0-2)
        gwd = gw.get("depth_to_water_table_m")
        if gwd is not None:
            if 1.0 <= gwd <= 10.0:
                score += 2
            elif 10.0 < gwd <= 30.0:
                score += 1

        # Water quality (0-1)
        wq = gw.get("water_quality_estimate", "")
        if "جيدة جداً" in wq or "جيدة" in wq:
            score += 1

        return max(1, min(10, score))

    # ──────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """حالة الخدمة ومصادر البيانات"""
        return {
            "gee_available": self.gee_available,
            "egsma_available": self.egsma_available,
            "egsma_status": self.egsma.status(),
            "profile_count": len(_EGYPT_SOIL_PROFILES),
            "resolution_order": ["gee", "egsma", "profile"],
            "always_available": True,  # profile fallback
        }

    def list_egypt_regions(self) -> List[Dict[str, Any]]:
        """قائمة المناطق الجيولوجية المصرية المتاحة في قاعدة البيانات"""
        return [
            {
                "region": p["region"],
                "region_en": p["region_en"],
                "center_lat": p["center"][0],
                "center_lon": p["center"][1],
                "soil_type": p["soil_type_ar"],
                "ph": p["ph"],
                "groundwater_depth_m": p["groundwater_depth_m"],
                "suitability": p["suitability"],
            }
            for p in _EGYPT_SOIL_PROFILES
        ]