"""
Google Earth Engine Client
===========================
غلاف GEE API — مصادقة، استعلام البكسل، استخراج بيانات حقيقية

GEE is free for non-commercial research use.
Authentication requires a one-time setup:
    1. Create account at https://code.earthengine.google.com/
    2. Run: earthengine authenticate  (in terminal)
    3. This creates ~/.config/earthengine/credentials

Datasets used:
    - ISRIC Soil Grids v1 (250m):
        users/isricorg/soilgrids250m/...  (public in GEE)
    - GLHYMPS v2.0:
        users/ujjawal/GLHYMPS  (public in GEE)

Fallback:
    If GEE is unavailable (no credentials / offline), all
    methods return None so callers can fall back to EGSMA
    or in-memory Egypt profile data.
"""

import os
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# GEE import is deferred — earthengine-api may not be installed
_ee = None


def _import_ee():
    """
    Import earthengine lazily.

    Returns ee module or None if not installed.
    """
    global _ee
    if _ee is not None:
        return _ee
    try:
        import ee
        _ee = ee
        return _ee
    except ImportError:
        logger.warning(
            "earthengine-api not installed. "
            "Install with: pip install earthengine-api"
        )
        return None


class GEEClient:
    """
    عميل Google Earth Engine — مصادقة + استعلام

    Usage:
        # With real GEE credentials:
        client = GEEClient(use_service_account=False)
        client.initialize()

        # Read pixel value:
        val = client.get_pixel_value(
            image_asset="USGS/SRTMGL1_003",
            bands=["elevation"],
            lat=30.0444,
            lon=31.2357,
            scale=30,
        )
        # val = {"elevation": 23}  (meters above sea level)
    """

    def __init__(
        self,
        use_service_account: bool = False,
        service_account_email: str = "",
        service_account_key_file: str = "",
        project: str = "",
    ):
        """
        Args:
            use_service_account: استخدام حساب خدمة بدلاً من المستخدم
            service_account_email: بريد حساب الخدمة
            service_account_key_file: مسار ملف JSON للمفتاح
            project: معرف مشروع GCP (مطلوب لحسابات الخدمة)
        """
        self.ee = None
        self.initialized = False
        self.use_service_account = use_service_account
        self.service_account_email = service_account_email
        self.service_account_key_file = service_account_key_file
        self.project = project

    # ──────────────────────────────────────────
    # Initialization
    # ──────────────────────────────────────────

    def initialize(self) -> bool:
        """
        تهيئة GEE — المصادقة وبدء الجلسة

        Returns:
            True إذا نجحت التهيئة
        """
        ee = _import_ee()
        if ee is None:
            logger.info("GEE: earthengine-api غير متاح")
            return False

        try:
            if self.use_service_account and self.service_account_key_file:
                credentials = ee.ServiceAccountCredentials(
                    self.service_account_email,
                    self.service_account_key_file,
                )
                ee.Initialize(credentials, project=self.project)
            else:
                # User credentials (from earthengine authenticate)
                ee.Initialize()

            self.ee = ee
            self.initialized = True
            logger.info("GEE: initialized successfully")
            return True

        except Exception as e:
            logger.error(f"GEE: initialization failed — {e}")
            self.initialized = False
            return False

    def is_ready(self) -> bool:
        """هل GEE جاهز للاستعلام؟"""
        if not self.initialized or self.ee is None:
            return False
        try:
            # Quick check — list a tiny collection
            self.ee.data.listAssets({"id": "USGS/SRTMGL1_003"})[:0]
            return True
        except Exception:
            return False

    # ──────────────────────────────────────────
    # Core Query Methods
    # ──────────────────────────────────────────

    def get_pixel_value(
        self,
        image_asset: str,
        bands: List[str],
        lat: float,
        lon: float,
        scale: int = 250,
        reducer: str = "first",
    ) -> Optional[Dict[str, Any]]:
        """
        استخراج قيمة بكسل واحد من صورة GEE

        Args:
            image_asset: مسار الصورة في GEE (مثال: "USGS/SRTMGL1_003")
            bands: أسماء النطاقات المطلوبة
            lat: خط العرض
            lon: خط الطول
            scale: دقة الاستخراج بالمتر
            reducer: دالة التجميع (first/mean/median)

        Returns:
            قاموس {band_name: value} أو None عند الفشل
        """
        if not self.is_ready():
            return None

        ee = self.ee
        try:
            # Load image
            image = ee.Image(image_asset)
            point = ee.Geometry.Point([lon, lat])

            # Select requested bands
            if bands:
                image = image.select(bands)

            # Reduce region to single point
            if reducer == "mean":
                ee_reducer = ee.Reducer.mean()
            elif reducer == "median":
                ee_reducer = ee.Reducer.median()
            else:
                ee_reducer = ee.Reducer.first()

            result = image.reduceRegion(
                reducer=ee_reducer,
                geometry=point.buffer(scale / 2, 1),  # small buffer
                scale=scale,
                bestEffort=True,
                maxPixels=1,
            )

            # getInfo() makes the actual API call
            values = result.getInfo()

            if not values:
                return None

            # Filter to requested bands only
            filtered = {}
            for band in bands:
                val = values.get(band)
                if val is not None:
                    # Round floats for readability
                    if isinstance(val, float):
                        filtered[band] = round(val, 4)
                    else:
                        filtered[band] = val

            return filtered if filtered else None

        except Exception as e:
            logger.error(f"GEE get_pixel_value failed for {image_asset}: {e}")
            return None

    def get_time_series(
        self,
        collection_asset: str,
        bands: List[str],
        lat: float,
        lon: float,
        scale: int = 250,
        start_date: str = "2020-01-01",
        end_date: str = "2024-12-31",
        reducer: str = "mean",
    ) -> Optional[List[Dict[str, Any]]]:
        """
        استخراج سلسلة زمنية من مجموعة صور GEE

        Args:
            collection_asset: مسار المجموعة
            bands: النطاقات
            lat, lon: الإحداثيات
            scale: الدقة
            start_date: تاريخ البداية
            end_date: تاريخ النهاية
            reducer: دالة التجميع

        Returns:
            قائمة بالقيم لكل تاريخ
        """
        if not self.is_ready():
            return None

        ee = self.ee
        try:
            collection = ee.ImageCollection(collection_asset) \
                .filterDate(start_date, end_date) \
                .select(bands)

            point = ee.Geometry.Point([lon, lat])

            # Reduce each image in collection to the point
            def reduce_image(img):
                result = img.reduceRegion(
                    reducer=ee.Reducer.first(),
                    geometry=point.buffer(scale / 2, 1),
                    scale=scale,
                    bestEffort=True,
                    maxPixels=1,
                )
                return img.set("values", result)

            reduced = collection.map(reduce_image)

            # Get all values
            info = reduced.toList(reduced.size()).getInfo()

            results = []
            for item in info:
                if isinstance(item, dict):
                    date = item.get("system:time_start", "")
                    values = item.get("values", {})
                    entry = {"date": date}
                    for band in bands:
                        if band in values and values[band] is not None:
                            val = values[band]
                            entry[band] = round(val, 4) if isinstance(val, float) else val
                    results.append(entry)

            return results if results else None

        except Exception as e:
            logger.error(f"GEE time_series failed: {e}")
            return None

    def get_image_property(
        self,
        image_asset: str,
        properties: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        استرجاع خصائص صورة (metadata) بدون تحميل البيانات

        Args:
            image_asset: مسار الصورة
            properties: قائمة أسماء الخصائص

        Returns:
            قاموس بالخصائص
        """
        if not self.is_ready():
            return None

        ee = self.ee
        try:
            image = ee.Image(image_asset)
            info = image.getInfo()
            if not info:
                return None

            return {p: info.get(p) for p in properties if p in info}

        except Exception as e:
            logger.error(f"GEE get_image_property failed: {e}")
            return None