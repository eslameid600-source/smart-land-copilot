"""
EGSMA GeoTIFF Reader
=====================
قارئ ملفات EGSMA (الهيئة المصرية للمسح الجيولوجي) عبر rasterio

EGSMA publishes geological maps as GeoTIFF files covering Egypt:
    - Soil type maps
    - Geological structure maps
    - Hydrogeological maps
    - Mineral resources maps

These can be downloaded from:
    - EGSMA website: https://www.egsma.gov.eg
    - Ministry of Water Resources / NARSS
    - Open data portals (when available)

File naming convention (expected):
    data/geological/egsma/
        soil_type_egypt.tif
        ph_egypt.tif
        organic_matter_egypt.tif
        groundwater_depth_egypt.tif
        geology_egypt.tif

Usage:
    reader = EGSMAReader(data_dir="/path/to/egsma/geotiffs")

    # Check available layers
    print(reader.list_layers())

    # Read soil pH at a point
    val = reader.read_point("ph_egypt.tif", 30.0444, 31.2357)

    # Read soil type (categorical raster)
    val, label = reader.read_categorical(
        "soil_type_egypt.tif", 30.0444, 31.2357,
        legend={1: "رملية", 2: "طينية", 3: "مزيجية", ...}
    )
"""

import logging
import os
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Rasterio Import (deferred)
# ──────────────────────────────────────────────

_rasterio = None


def _import_rasterio():
    """استيراد rasterio بـ lazy loading"""
    global _rasterio
    if _rasterio is not None:
        return _rasterio
    try:
        import rasterio as rio
        _rasterio = rio
        return _rasterio
    except ImportError:
        logger.warning(
            "rasterio not installed. "
            "Install with: pip install rasterio"
        )
        return None


# ──────────────────────────────────────────────
# EGSMA Legend Mappings
# ──────────────────────────────────────────────

# إعادة تصنيف أنواع التربة المصرية (FAO/EGSMA codes)
# هذه الخرائط من EGSMA تستخدم ترميزاً خاصاً

EGSMA_SOIL_LEGEND = {
    # Major soil great groups found in Egypt
    1:  ("ريج صحراوي", "Desert Soil"),
    2:  ("ريج", "Nile Alluvial"),
    3:  ("طينة النيل", "Nile Clay"),
    4:  ("لوحية", "Calcareous Soil"),
    5:  ("ملحية", "Saline Soil"),
    6:  ("جبسية", "Gypsiferous Soil"),
    7:  ("رملية ساحلية", "Coastal Sandy"),
    8:  ("سبخة", "Sabkha/Salt Flat"),
    9:  ("حجرية", "Lithic/Rocky"),
    10: ("رمال كثيفة", "Aeolian Sand Dunes"),
    11: ("ترابية حمراء", "Terra Rossa"),
    12: ("غابية سوداء", "Chernozem-like"),
}

# تصنيف جودة التربة للاستثمار
EGSMA_SOIL_SUITABILITY = {
    1:  ("محدود", 3),
    2:  ("ممتاز", 10),
    3:  ("جيد جداً", 9),
    4:  ("جيد", 7),
    5:  ("ضعيف", 2),
    6:  ("محدود", 3),
    7:  ("محدود", 4),
    8:  ("غير مناسب", 1),
    9:  ("غير مناسب لزراعة", 1),
    10: ("محدود جداً", 2),
    11:  ("متوسط", 5),
    12:  ("جيد", 8),
}


class EGSMAReader:
    """
    قارئ ملفات EGSMA GeoTIFF

    Features:
        - قراءة قيمة بكسل في نقطة محددة (lat, lon)
        - دعم النطاقات المتعددة (multi-band)
        - خرائط تصنيفية مع قاموس لegend
        - فحص توفر الملفات
        - ملفات في الذاكرة (mock) للاختبار

    Usage:
        reader = EGSMAReader(data_dir="./data/geological/egsma")

        # List available files
        print(reader.list_layers())

        # Read continuous value (e.g., pH)
        ph_val = reader.read_point("ph_egypt.tif", 30.04, 31.24)

        # Read categorical (e.g., soil type with legend)
        code, label_ar, label_en = reader.read_categorical(
            "soil_type_egypt.tif", 30.04, 31.24,
            legend=EGSMA_SOIL_LEGEND,
        )

        # Read with custom band
        val = reader.read_point("multi_band.tif", 30.04, 31.24, band=2)
    """

    # Expected file names
    EXPECTED_FILES = {
        "soil_type": "soil_type_egypt.tif",
        "ph": "ph_egypt.tif",
        "organic_matter": "organic_matter_egypt.tif",
        "groundwater_depth": "groundwater_depth_egypt.tif",
        "geology": "geology_egypt.tif",
        "elevation": "srtm_egypt.tif",
        "slope": "slope_egypt.tif",
    }

    def __init__(self, data_dir: str = ""):
        """
        Args:
            data_dir: مسار مجلد ملفات GeoTIFF
        """
        self.data_dir = data_dir
        self._available_layers: Dict[str, str] = {}
        self._rio = None

        # Scan directory
        if data_dir and os.path.isdir(data_dir):
            self._scan_directory()

        logger.info(
            f"EGSMAReader initialized | data_dir={data_dir} | "
            f"layers_found={len(self._available_layers)}"
        )

    # ──────────────────────────────────────────
    # Directory Management
    # ──────────────────────────────────────────

    def _scan_directory(self) -> None:
        """فحص المجلد واكتشاف ملفات GeoTIFF"""
        rio = _import_rasterio()
        if rio is None:
            return

        if not os.path.isdir(self.data_dir):
            return

        for fname in os.listdir(self.data_dir):
            fpath = os.path.join(self.data_dir, fname)
            if fname.endswith((".tif", ".tiff")):
                try:
                    with rio.open(fpath) as src:
                        # Use filename without extension as key
                        key = os.path.splitext(fname)[0]
                        self._available_layers[key] = fpath
                except Exception as e:
                    logger.warning(f"Cannot open {fname}: {e}")

    def list_layers(self) -> Dict[str, str]:
        """
        قائمة الطبقات المتاحة

        Returns:
            {layer_name: file_path}
        """
        return dict(self._available_layers)

    def is_layer_available(self, layer_name: str) -> bool:
        """هل الطبقة متاحة؟"""
        return layer_name in self._available_layers

    def add_layer(self, name: str, file_path: str) -> bool:
        """
        إضافة طبقة يدوياً

        Args:
            name: اسم الطبقة
            file_path: مسار الملف

        Returns:
            True إذا نجح
        """
        if os.path.isfile(file_path):
            self._available_layers[name] = file_path
            return True
        return False

    # ──────────────────────────────────────────
    # Point Extraction
    # ──────────────────────────────────────────

    def read_point(
        self,
        layer_name: str,
        lat: float,
        lon: float,
        band: int = 1,
        nodata_value: Optional[float] = None,
    ) -> Optional[float]:
        """
        قراءة قيمة بكسل واحد من ملف GeoTIFF

        Args:
            layer_name: اسم الطبقة (مثال: "ph_egypt")
            lat: خط العرض
            lon: خط الطول
            band: رقم النطاق (1-indexed)
            nodata_value: قيمة NoData لتجاهلها

        Returns:
            القيمة العددية أو None
        """
        rio = _import_rasterio()
        if rio is None:
            logger.warning("rasterio not available")
            return None

        # Find file
        fpath = self._resolve_path(layer_name)
        if fpath is None:
            logger.warning(f"Layer '{layer_name}' not found")
            return None

        try:
            with rio.open(fpath) as src:
                # Convert lat/lon to pixel coordinates
                row, col = src.index(lon, lat)

                # Bounds check
                if row < 0 or row >= src.height or col < 0 or col >= src.width:
                    logger.debug(f"Point ({lat}, {lon}) outside raster bounds")
                    return None

                # Read single pixel
                band_idx = band - 1  # 0-indexed
                if band_idx >= src.count:
                    logger.warning(f"Band {band} not available (max: {src.count})")
                    return None

                window = rio.windows.Window(col, row, 1, 1)
                data = src.read(band_idx, window=window)

                val = float(data[0, 0])

                # Check NoData
                if nodata_value is not None and abs(val - nodata_value) < 1e-6:
                    return None
                if src.nodata is not None and abs(val - src.nodata) < 1e-6:
                    return None

                # Check for very large values (often indicates nodata)
                if abs(val) > 1e10:
                    return None

                return round(val, 4)

        except Exception as e:
            logger.error(f"Error reading {layer_name} at ({lat}, {lon}): {e}")
            return None

    def read_categorical(
        self,
        layer_name: str,
        lat: float,
        lon: float,
        legend: Dict[int, Tuple[str, str]],
        band: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """
        قراءة قيمة تصنيفية مع فك الترميز

        Args:
            layer_name: اسم الطبقة
            lat, lon: الإحداثيات
            legend: قاموس الترميز {code: (arabic_label, english_label)}
            band: رقم النطاق

        Returns:
            {
                "value": 3,
                "label_ar": "طينة النيل",
                "label_en": "Nile Clay",
                "legend_key": 3,
            }
        """
        raw = self.read_point(layer_name, lat, lon, band=band)
        if raw is None:
            return None

        code = int(raw)
        ar, en = legend.get(code, ("غير معروف", "Unknown"))

        return {
            "value": code,
            "label_ar": ar,
            "label_en": en,
        }

    def read_profile(
        self,
        lat: float,
        lon: float,
        layers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        قراءة ملف تعريف كامل لكل الطبقات المتاحة

        Args:
            lat, lon: الإحداثيات
            layers: خريطة مخصصة {output_key: layer_name}

        Returns:
            {output_key: value} لكل طبقة متاحة
        """
        if layers is None:
            layers = {
                "soil_type": "soil_type_egypt",
                "ph": "ph_egypt",
                "organic_matter": "organic_matter_egypt",
                "groundwater_depth": "groundwater_depth_egypt",
            }

        profile = {"latitude": lat, "longitude": lon, "source": "egsma"}

        for out_key, layer_name in layers.items():
            if self.is_layer_available(layer_name):
                val = self.read_point(layer_name, lat, lon)
                profile[out_key] = val

        return profile

    # ──────────────────────────────────────────
    # Raster Metadata
    # ──────────────────────────────────────────

    def get_raster_info(self, layer_name: str) -> Optional[Dict[str, Any]]:
        """
        استرجاع معلومات ملف GeoTIFF (CRS, bounds, resolution, bands)

        Args:
            layer_name: اسم الطبقة

        Returns:
            {
                "width": 1000,
                "height": 800,
                "bands": 1,
                "crs": "EPSG:4326",
                "bounds": {"left": 24.0, "bottom": 21.0, "right": 37.0, "top": 32.0},
                "resolution": [0.0025, 0.0025],
                "nodata": -9999,
            }
        """
        rio = _import_rasterio()
        if rio is None:
            return None

        fpath = self._resolve_path(layer_name)
        if fpath is None:
            return None

        try:
            with rio.open(fpath) as src:
                bounds = src.bounds
                return {
                    "width": src.width,
                    "height": src.height,
                    "bands": src.count,
                    "crs": str(src.crs) if src.crs else "unknown",
                    "bounds": {
                        "left": bounds.left,
                        "bottom": bounds.bottom,
                        "right": bounds.right,
                        "top": bounds.top,
                    },
                    "resolution": list(src.res),
                    "nodata": src.nodata,
                    "dtype": str(src.dtypes[0]),
                    "driver": src.driver,
                }
        except Exception as e:
            logger.error(f"Error reading info for {layer_name}: {e}")
            return None

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _resolve_path(self, layer_name: str) -> Optional[str]:
        """إيجاد مسار الملف بالاسم"""
        # Direct match
        if layer_name in self._available_layers:
            return self._available_layers[layer_name]

        # Try with .tif extension
        tif_name = layer_name if layer_name.endswith(".tif") else f"{layer_name}.tif"
        if tif_name in self._available_layers:
            return self._available_layers[tif_name]

        # Try without _egypt suffix
        base = layer_name.replace("_egypt", "").replace(".tif", "")
        for key, path in self._available_layers.items():
            if base in key:
                return path

        return None

    def status(self) -> Dict[str, Any]:
        """حالة القارئ — هل المتطلبات متوفرة؟"""
        rio = _import_rasterio()
        return {
            "rasterio_available": rio is not None,
            "data_dir": self.data_dir,
            "data_dir_exists": os.path.isdir(self.data_dir) if self.data_dir else False,
            "layers_found": len(self._available_layers),
            "layers": list(self._available_layers.keys()),
        }