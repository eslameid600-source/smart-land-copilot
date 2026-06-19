"""
Smart Land Management Copilot — Environmental & Creator Proximity Service
========================================================================
Geospatial and utility metadata scoring calculator for:

1. Greenery Density Index:
   Analyzes proximity to public parks and green spaces
   (ارض خضراء وحدائق) for corporate wellness, residential
   appeal, and mental peace.

2. Content Creator Studio Suitability Score:
   Engineering suitability rating (0-100) for spaces intended
   for digital production studios, 3D graphics agencies, and
   YouTube creators. Weighs ultra-low ambient noise / high
   greenery landscape and mandatory Fiber Optic infrastructure
   (ألياف ضوئية) for massive data uploads.
"""
import math
import logging
from typing import Dict, Optional, List
from models.models.models.land import GreeneryDensityData, CreatorStudioSuitability, EnvironmentalData
logger = logging.getLogger(__name__)
EGYPTIAN_GREEN_SPACES = {'Cairo': {'parks': [{'name': 'Al-Azhar Park', 'lat': 30.0457, 'lon': 31.262, 'area_ha': 30}, {'name': 'Family Park New Cairo', 'lat': 30.016, 'lon': 31.44, 'area_ha': 20}, {'name': 'International Garden', 'lat': 30.058, 'lon': 31.331, 'area_ha': 35}, {'name': 'Orman Botanical Garden', 'lat': 30.0195, 'lon': 31.2092, 'area_ha': 8}, {'name': 'Gabalaya Park', 'lat': 30.053, 'lon': 31.218, 'area_ha': 5}]}, 'Giza': {'parks': [{'name': 'Giza Zoo & Gardens', 'lat': 30.0284, 'lon': 31.2158, 'area_ha': 34}, {'name': 'Fustat Gardens', 'lat': 30.005, 'lon': 31.236, 'area_ha': 12}, {'name': 'Oasis Park 6th October', 'lat': 29.959, 'lon': 30.901, 'area_ha': 15}]}, 'Alexandria': {'parks': [{'name': 'Montaza Palace Gardens', 'lat': 31.2985, 'lon': 30.0193, 'area_ha': 60}, {'name': 'Antoniadis Garden', 'lat': 31.203, 'lon': 29.908, 'area_ha': 40}, {'name': 'Alexandria Zoo', 'lat': 31.2089, 'lon': 29.9103, 'area_ha': 10}]}, 'Suez': {'parks': [{'name': 'Suez Public Park', 'lat': 29.9668, 'lon': 32.5498, 'area_ha': 8}]}, 'Ismailia': {'parks': [{'name': 'Ismailia Green Island', 'lat': 30.592, 'lon': 32.271, 'area_ha': 12}, {'name': 'Ismailia Public Garden', 'lat': 30.595, 'lon': 32.265, 'area_ha': 6}]}}

class EnvironmentalService:
    """
    Analyzes environmental suitability of land parcels for
    greenery proximity and content creator studio use.
    """

    def __init__(self):
        self._cache: Dict[str, EnvironmentalData] = {}

    def analyze(self, land_dict: Dict) -> EnvironmentalData:
        """
        Run the full environmental analysis suite on a land record.

        Returns an EnvironmentalData object containing both
        GreeneryDensityData and CreatorStudioSuitability.
        """
        land_id = land_dict.get('Land_ID', '')
        if land_id in self._cache:
            return self._cache[land_id]
        greenery = self.compute_greenery_index(land_dict)
        creator = self.compute_creator_studio_score(land_dict, greenery)
        result = EnvironmentalData(greenery=greenery, creator_studio=creator)
        self._cache[land_id] = result
        return result

    def compute_greenery_index(self, land_dict: Dict) -> GreeneryDensityData:
        """
        Compute the Greenery Density Index for a land parcel.

        Scoring formula:
        - Proximity factor (0-40 pts): Closer nearest park = higher score
        - Park count factor (0-30 pts): More parks within 5km = higher score
        - Green area factor (0-30 pts): Larger total green area = higher score
        """
        lat = land_dict.get('Latitude', 0)
        lon = land_dict.get('Longitude', 0)
        governorate = land_dict.get('Governorate', '')
        parks = EGYPTIAN_GREEN_SPACES.get(governorate, {}).get('parks', [])
        if not parks:
            return GreeneryDensityData(greenery_density_index=0.0, greenery_verdict=f'No green space data available for {governorate}')
        distances = []
        for park in parks:
            dist = self._haversine_km(lat, lon, park['lat'], park['lon'])
            distances.append({'name': park['name'], 'distance_km': dist, 'area_ha': park['area_ha']})
        distances.sort(key=lambda x: x['distance_km'])
        nearest = distances[0]
        parks_2km = sum((1 for d in distances if d['distance_km'] <= 2.0))
        parks_5km = sum((1 for d in distances if d['distance_km'] <= 5.0))
        total_green_ha = sum((d['area_ha'] for d in distances if d['distance_km'] <= 5.0))
        if nearest['distance_km'] <= 0.5:
            proximity_score = 40.0
        elif nearest['distance_km'] <= 1.0:
            proximity_score = 35.0
        elif nearest['distance_km'] <= 2.0:
            proximity_score = 25.0
        elif nearest['distance_km'] <= 5.0:
            proximity_score = 15.0
        elif nearest['distance_km'] <= 10.0:
            proximity_score = 8.0
        else:
            proximity_score = 3.0
        count_score = min(parks_5km * 8, 30.0)
        if total_green_ha > 0:
            area_score = min(math.log10(total_green_ha + 1) * 15, 30.0)
        else:
            area_score = 0.0
        index = round(min(proximity_score + count_score + area_score, 100.0), 1)
        if index >= 70:
            verdict = 'Excellent greenery environment — premium wellness and residential appeal'
        elif index >= 45:
            verdict = 'Good greenery access — suitable for residential and mixed-use developments'
        elif index >= 20:
            verdict = 'Moderate greenery — some parks in the wider area'
        else:
            verdict = 'Low greenery density — industrial or remote location'
        return GreeneryDensityData(nearest_park_name=nearest['name'], nearest_park_distance_km=round(nearest['distance_km'], 2), parks_within_2km=parks_2km, parks_within_5km=parks_5km, total_green_area_hectares=round(total_green_ha, 1), greenery_density_index=index, greenery_verdict=verdict)

    def compute_creator_studio_score(self, land_dict: Dict, greenery: GreeneryDensityData) -> CreatorStudioSuitability:
        """
        Compute the Content Creator Studio Suitability Score (0-100).

        Two critical inputs weighted equally (max 50 pts each):
        1. Greenery / Low-Noise Environment Factor (max 50 pts):
           Uses greenery density as a proxy for low ambient noise.
        2. Fiber Optic Infrastructure Factor (max 50 pts):
           Mandatory high-speed fiber for massive data uploads.
        """
        utilities = land_dict.get('Utilities_Availability', '')
        usage = land_dict.get('Allowed_Usage', '')
        infrastructure = land_dict.get('Infrastructure', {})
        greenery_score = greenery.greenery_density_index
        noise_rating = 'Unknown'
        if usage == 'Industrial':
            noise_rating = 'Industrial'
            noise_penalty = 0.3
        elif usage == 'Logistics':
            noise_rating = 'High'
            noise_penalty = 0.5
        elif usage == 'Residential':
            noise_rating = 'Low'
            noise_penalty = 0.9
        else:
            noise_rating = 'Moderate'
            noise_penalty = 0.7
        greenery_factor = round(min(greenery_score * noise_penalty, 50.0), 1)
        has_fiber = 'Fiber-Optic' in utilities or 'Fiber Optic' in utilities
        internet_speed = 0
        if infrastructure:
            internet_speed = infrastructure.get('internet_speed_mbps', 0) or 0
        if not internet_speed and has_fiber:
            internet_speed = 500
        if internet_speed >= 1000:
            fiber_factor = 50.0
        elif internet_speed >= 500:
            fiber_factor = 42.0
        elif internet_speed >= 200:
            fiber_factor = 35.0
        elif internet_speed >= 100:
            fiber_factor = 25.0
        elif has_fiber:
            fiber_factor = 20.0
        else:
            fiber_factor = 0.0
        power_stability = 'Unknown'
        if 'Electricity' in utilities:
            power_stability = 'Stable (National Grid)'
        else:
            power_stability = 'No Grid Connection'
        total_score = round(min(greenery_factor + fiber_factor, 100.0), 1)
        if total_score >= 75:
            verdict = 'Highly suitable for content creation studios — excellent environment and connectivity'
        elif total_score >= 55:
            verdict = 'Suitable for digital production with minor infrastructure upgrades'
        elif total_score >= 30:
            verdict = 'Partially suitable — fiber optic installation recommended before studio setup'
        elif total_score > 0:
            verdict = 'Not recommended — significant infrastructure and environmental gaps'
        else:
            verdict = 'Unsuitable for creator studio use'
        if not has_fiber and total_score > 30:
            verdict += ' (Critical: Fiber optic required)'
        return CreatorStudioSuitability(suitability_score=total_score, noise_level_rating=noise_rating, greenery_factor=greenery_factor, fiber_optic_factor=fiber_factor, fiber_optic_available=has_fiber, internet_speed_mbps=internet_speed, power_stability_rating=power_stability, suitability_verdict=verdict)

    def analyze_all(self, lands: List[Dict]) -> Dict[str, EnvironmentalData]:
        """Batch analysis of all land records."""
        results = {}
        for land in lands:
            results[land.get('Land_ID', '')] = self.analyze(land)
        return results

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great-circle distance between two points in kilometers."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
_environmental_service: Optional[EnvironmentalService] = None

def get_environmental_service() -> EnvironmentalService:
    global _environmental_service
    if _environmental_service is None:
        _environmental_service = EnvironmentalService()
    return _environmental_service