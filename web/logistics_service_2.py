"""
Smart Land Management Copilot — Logistics & Supply Chain Intelligence Service
==============================================================================
Advanced logistics analysis for Egyptian land parcels.

Computes:
  1. Fleet Maintenance & Road Quality Factor
  2. Fuel Consumption Engine (Diesel / Solar-assisted)
  3. Air Freight & Cargo Airport Connectivity
  4. Rail Freight Integration (Conventional + High-Speed Electric)
  5. Logistics Feasibility Matrix (composite investor-grade output)
"""

from typing import Dict, List

from models.land import (AirFreightConnectivity, CargoAirportTier,
                         FleetMaintenanceImpact, FuelTripEstimate, FuelType,
                         LogisticsMeta, RailFreightIntegration,
                         RailNetworkType, RoadQuality)

# ────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────

_ROAD_QUALITY_SCORES: Dict[RoadQuality, float] = {
    RoadQuality.EXCELLENT: 1.00,
    RoadQuality.GOOD: 0.85,
    RoadQuality.AVERAGE: 0.65,
    RoadQuality.POOR: 0.40,
    RoadQuality.UNPAVED: 0.15,
}

# Fleet maintenance overhead percentages vs Excellent baseline.
# Based on Egyptian transport authority data for heavy-truck fleets.
_FLEET_MAINTENANCE_OVERHEAD: Dict[RoadQuality, float] = {
    RoadQuality.EXCELLENT: 0.0,
    RoadQuality.GOOD: 12.0,
    RoadQuality.AVERAGE: 28.0,
    RoadQuality.POOR: 52.0,
    RoadQuality.UNPAVED: 85.0,
}

# Primary wear factors per road quality level
_ROAD_WEAR_FACTORS: Dict[RoadQuality, List[str]] = {
    RoadQuality.EXCELLENT: [
        "Standard tire rotation schedule",
        "Minimal suspension stress",
    ],
    RoadQuality.GOOD: [
        "Accelerated tire wear from minor surface irregularities",
        "Moderate brake pad usage from occasional speed changes",
    ],
    RoadQuality.AVERAGE: [
        "Frequent tire replacement due to road surface degradation",
        "Suspension component fatigue from uneven surfaces",
        "Increased fuel filter replacement frequency",
    ],
    RoadQuality.POOR: [
        "Severe tire damage from potholes and loose gravel",
        "Accelerated suspension and chassis wear",
        "Frequent undercarriage repairs from road debris",
        "Higher engine load from low-gear driving on degraded roads",
        "Increased risk of cargo damage during transit",
    ],
    RoadQuality.UNPAVED: [
        "Extreme tire consumption on unpaved surfaces",
        "Critical suspension failure risk on rough terrain",
        "Dust and sand infiltration damaging engine and braking systems",
        "Axle and drivetrain overstrain from soft-ground navigation",
        "Frequent vehicle downtime for emergency repairs",
        "Cargo integrity at high risk without specialized vehicles",
    ],
}

# Baseline annual fleet maintenance cost per truck (EGP) for Excellent roads.
# Covers tires, brakes, suspension, oil changes, minor repairs.
_BASELINE_ANNUAL_MAINT_PER_TRUCK_EGP = 85_000
_REFERENCE_FLEET_SIZE = 50

# ── Fuel consumption engine constants ──

# Egyptian diesel price (EGP/liter) — as of mid-2026 market rates
_DIESEL_PRICE_PER_LITER_EGP = 15.50

# Heavy truck fuel consumption: liters per km (laden, 20-ton payload)
_DIESEL_LITERS_PER_KM = 0.38

# Solar-assisted hybrid trucks achieve lower effective consumption.
# Solar panels offset auxiliary systems (AC, hydraulics, refrigeration).
_SOLAR_DIESEL_LITERS_PER_KM = 0.33

# Solar savings percentage = 1 - (SOLAR_DIESEL / DIESEL) ≈ 13.2%
_SOLAR_SAVINGS_PCT = round((1.0 - _SOLAR_DIESEL_LITERS_PER_KM / _DIESEL_LITERS_PER_KM) * 100, 1)

# Working days per year for annual cost projection
_ANNUAL_TRIP_DAYS = 250

# Reference truck payload in tons (for per-ton-km cost)
_REFERENCE_TRUCK_PAYLOAD_TONS = 20.0

# ── Scoring weights ──

_HW_MAX_KM = 20.0
_PORT_MAX_KM = 100.0
_CARGO_AIRPORT_MAX_KM = 80.0

# ── Cargo airport reference data ──

_CARGO_AIRPORT_REGISTRY: Dict[str, Dict] = {
    "Cairo International Airport": {
        "tier": CargoAirportTier.TIER_1_MAJOR,
        "daily_capacity_tons": 1200.0,
        "perishable_export": True,
    },
    "Borg El Arab Airport": {
        "tier": CargoAirportTier.TIER_2_REGIONAL,
        "daily_capacity_tons": 150.0,
        "perishable_export": True,
    },
    "Sphinx International Airport": {
        "tier": CargoAirportTier.TIER_2_REGIONAL,
        "daily_capacity_tons": 80.0,
        "perishable_export": True,
    },
    "Aswan International Airport": {
        "tier": CargoAirportTier.TIER_2_REGIONAL,
        "daily_capacity_tons": 40.0,
        "perishable_export": False,
    },
}

# ── Rail freight constants ──

# Cost saving percentages for rail vs truck-only transport
_RAIL_COST_SAVINGS: Dict[RailNetworkType, float] = {
    RailNetworkType.HIGH_SPEED_ELECTRIC: 40.0,
    RailNetworkType.CONVENTIONAL_FREIGHT: 25.0,
    RailNetworkType.NONE: 0.0,
}

# Minimum tonnage threshold for "heavy-tonnage viable" classification
_HEAVY_TONNAGE_THRESHOLD_TONS_PER_DAY = 500.0


class LogisticsService:
    """
    Computes and analyzes the Logistics & Supply Chain Intelligence Factor.

    Evaluates how well-suited each land parcel is for logistics and
    warehousing operations by scoring and analyzing:
      - Fleet maintenance impact from Road Quality Index
      - Fuel consumption engine (Diesel / Solar-assisted) to nearest port
      - Air freight connectivity to cargo-enabled airports
      - Rail freight integration (conventional + high-speed electric)
      - Composite accessibility score and logistics feasibility matrix
    """

    def analyze(self, land: Dict) -> LogisticsMeta:
        """
        Run full logistics analysis on a land record.

        Expects the land dict to contain a 'logistics_meta' sub-dict
        with the raw logistics fields. If missing, returns safe defaults.
        """
        raw = land.get("logistics_meta", {})

        road_quality = RoadQuality(raw.get("road_quality", "Average"))
        accessibility = self._compute_accessibility(raw, road_quality)
        verdict = self._generate_verdict(accessibility, raw, land)

        fleet_maintenance = self._compute_fleet_maintenance(road_quality, land)
        fuel_trip = self._compute_fuel_consumption(raw, road_quality, land)
        air_freight = self._compute_air_freight_connectivity(raw)
        rail_freight = self._compute_rail_freight(raw)

        return LogisticsMeta(
            nearest_highway_km=raw.get("nearest_highway_km"),
            road_quality=road_quality,
            nearest_cargo_airport_km=raw.get("nearest_cargo_airport_km"),
            rail_freight_access=raw.get("rail_freight_access", False),
            rail_station_name=raw.get("rail_station_name", ""),
            estimated_fuel_cost_per_trip_egp=raw.get("estimated_fuel_cost_per_trip_egp"),
            nearest_port_name=raw.get("nearest_port_name", ""),
            container_handling_nearby=raw.get("container_handling_nearby", False),
            cold_chain_available=raw.get("cold_chain_available", False),
            avg_truck_turnaround_hours=raw.get("avg_truck_turnaround_hours"),
            accessibility_score=accessibility,
            logistics_verdict=verdict,
            fleet_maintenance=fleet_maintenance,
            fuel_trip=fuel_trip,
            air_freight=air_freight,
            rail_freight=rail_freight,
        )

    def analyze_all(self, lands: List[Dict]) -> Dict[str, LogisticsMeta]:
        """Run logistics analysis on all land records."""
        return {land["Land_ID"]: self.analyze(land) for land in lands}

    def rank_for_logistics(self, lands: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Rank all lands by logistics suitability.
        Returns list of {land_id, region, accessibility_score, verdict, highlights}.
        """
        results = []
        for land in lands:
            analysis = self.analyze(land)
            raw = land.get("logistics_meta", {})
            highlights = self._extract_highlights(analysis, raw, land)
            results.append({
                "land_id": land["Land_ID"],
                "governorate": land["Governorate"],
                "region": land["Region_City"],
                "usage": land["Allowed_Usage"],
                "accessibility_score": analysis.accessibility_score,
                "verdict": analysis.logistics_verdict,
                "highlights": highlights,
                "logistics": analysis,
            })
        results.sort(key=lambda x: x["accessibility_score"], reverse=True)
        return results[:top_k]

    # ────────────────────────────────────────────────────────
    # Report generation
    # ────────────────────────────────────────────────────────

    def generate_logistics_report(self, land: Dict) -> str:
        """
        Produce a formatted 'Logistics & Freight Analysis' string
        for injection into LLM context or feasibility reports.
        """
        analysis = self.analyze(land)
        land.get("logistics_meta", {})
        land_id = land["Land_ID"]
        region = f"{land['Governorate']} - {land['Region_City']}"

        lines = [
            f"LOGISTICS & FREIGHT ANALYSIS -- {land_id} ({region})",
            "=" * 55,
            f"Composite Accessibility Score: {analysis.accessibility_score:.1f}/100",
            "",
            "TRANSPORTATION ACCESS:",
        ]

        hw = analysis.nearest_highway_km
        if hw is not None:
            lines.append(f"  Nearest Highway:  {hw:.1f} km")
        else:
            lines.append("  Nearest Highway:  N/A")

        lines.append(f"  Road Quality:     {analysis.road_quality.value}")

        port_dist = land.get("Nearest_Port_km")
        if port_dist is not None:
            lines.append(f"  Nearest Port:     {port_dist:.0f} km ({analysis.nearest_port_name or 'N/A'})")

        air = analysis.nearest_cargo_airport_km
        if air is not None:
            lines.append(f"  Cargo Airport:   {air:.0f} km")
        else:
            lines.append("  Cargo Airport:   N/A")

        lines.append(f"  Rail Freight:     {'Yes' if analysis.rail_freight_access else 'No'}")
        if analysis.rail_freight_access and analysis.rail_station_name:
            lines.append(f"    Station:         {analysis.rail_station_name}")

        # ── Fleet Maintenance & Road Quality Factor ──
        lines.extend(["", "FLEET MAINTENANCE & ROAD QUALITY FACTOR:"])
        if analysis.fleet_maintenance:
            fm = analysis.fleet_maintenance
            lines.append(f"  Road Quality Index:      {fm.road_quality_index.value}")
            lines.append(f"  Maintenance Overhead:    +{fm.maintenance_overhead_pct:.0f}% vs Excellent baseline")
            if fm.estimated_annual_maintenance_egp is not None:
                lines.append(
                    f"  Est. Annual Maintenance:  {fm.estimated_annual_maintenance_egp:,.0f} EGP "
                    f"({_REFERENCE_FLEET_SIZE}-truck fleet)"
                )
            lines.append("  Key Wear Factors:")
            for factor in fm.wear_factors:
                lines.append(f"    - {factor}")
        else:
            lines.append("  Road quality data not available")

        # ── Fuel Consumption Engine ──
        lines.extend(["", "FUEL CONSUMPTION ENGINE:"])
        if analysis.fuel_trip:
            ft = analysis.fuel_trip
            lines.append(f"  Fuel Type:               {ft.fuel_type.value}")
            lines.append(f"  Distance to Port:        {ft.distance_km:.0f} km one-way")
            lines.append(f"  Consumption (one-way):   {ft.consumption_liters:.1f} liters")
            lines.append(f"  Cost per Round-Trip:     {ft.cost_per_trip_egp:,.0f} EGP")
            lines.append(f"  Cost per Ton-km:         {ft.cost_per_ton_km_egp:.2f} EGP/ton-km")
            if ft.solar_savings_pct > 0:
                lines.append(
                    f"  Solar-Assisted Savings:   {ft.solar_savings_pct:.1f}% "
                    f"(Hybrid fleet reduces fuel cost to "
                    f"{ft.cost_per_trip_egp * (1 - ft.solar_savings_pct / 100):,.0f} EGP/trip)"
                )
            lines.append(f"  Est. Annual Fuel Cost:    {ft.annual_fuel_cost_egp:,.0f} EGP ({_ANNUAL_TRIP_DAYS} trips)")
        else:
            fuel = analysis.estimated_fuel_cost_per_trip_egp
            if fuel is not None:
                lines.append(f"  Est. Fuel Cost/Port Trip: {fuel:,.0f} EGP")
                annual_fuel = fuel * _ANNUAL_TRIP_DAYS
                lines.append(f"  Est. Annual Fuel Cost:    {annual_fuel:,.0f} EGP ({_ANNUAL_TRIP_DAYS} trips)")
            else:
                lines.append("  Est. Fuel Cost/Port Trip: N/A")

        # ── Air Freight & Cargo Airport Connectivity ──
        lines.extend(["", "AIR FREIGHT & CARGO AIRPORT CONNECTIVITY:"])
        if analysis.air_freight:
            af = analysis.air_freight
            lines.append(f"  Nearest Cargo Airport:  {af.nearest_cargo_airport or 'N/A'}")
            lines.append(f"  Airport Tier:           {af.airport_tier.value}")
            lines.append(f"  Distance:               {af.distance_km:.0f} km")
            lines.append(f"  Trucking Transit Time:  {af.trucking_transit_hours:.1f} hours")
            if af.daily_cargo_capacity_tons is not None:
                lines.append(f"  Daily Cargo Capacity:   {af.daily_cargo_capacity_tons:,.0f} tons")
            lines.append(
                f"  Perishable Export:      "
                f"{'Yes' if af.perishable_export_suitable else 'No'}"
            )
        else:
            lines.append("  Cargo airport data not available")

        # ── Rail Freight Integration ──
        lines.extend(["", "RAIL FREIGHT INTEGRATION:"])
        if analysis.rail_freight:
            rf = analysis.rail_freight
            lines.append(f"  Rail Access:             {'Yes' if rf.rail_access else 'No'}")
            lines.append(f"  Network Type:            {rf.network_type.value}")
            if rf.station_name:
                lines.append(f"  Station:                 {rf.station_name}")
                if rf.station_distance_km is not None:
                    lines.append(f"  Station Distance:        {rf.station_distance_km:.1f} km")
            if rf.estimated_tonnage_cost_saving_pct > 0:
                lines.append(
                    f"  Tonnage Cost Saving:     {rf.estimated_tonnage_cost_saving_pct:.0f}% "
                    f"vs truck-only"
                )
            lines.append(
                f"  Heavy-Tonnage Viable:    "
                f"{'Yes' if rf.heavy_tonnage_viable else 'No'} "
                f"(threshold: {_HEAVY_TONNAGE_THRESHOLD_TONS_PER_DAY:.0f} tons/day)"
            )
        else:
            lines.append(f"  Rail Freight Access:     {'Yes' if analysis.rail_freight_access else 'No'}")

        # ── Warehousing Support ──
        lines.extend(["", "WAREHOUSING SUPPORT:"])
        lines.append(
            f"  Container Handling Nearby:  {'Yes' if analysis.container_handling_nearby else 'No'}"
        )
        lines.append(
            f"  Cold Chain Available:       {'Yes' if analysis.cold_chain_available else 'No'}"
        )

        turnaround = analysis.avg_truck_turnaround_hours
        if turnaround is not None:
            lines.append(f"  Truck Turnaround:        {turnaround:.1f} hours")

        lines.extend(["", "VERDICT:", f"  {analysis.logistics_verdict}"])

        # Warnings for logistics/warehousing investors
        usage = land.get("Allowed_Usage", "")
        if usage in ("Logistics", "Industrial"):
            if analysis.accessibility_score < 30:
                lines.extend([
                    "",
                    "LOGISTICS SUITABILITY WARNING:",
                    f"  This land scores {analysis.accessibility_score:.0f}/100 on logistics accessibility. "
                    "For a logistics or warehousing project, this is below the recommended "
                    "threshold of 40. High transportation costs and limited multimodal access "
                    "may significantly impact operating margins.",
                ])
            elif analysis.accessibility_score >= 70:
                lines.extend([
                    "",
                    "LOGISTICS SUITABILITY: STRONG",
                    f"  Excellent multimodal access (score {analysis.accessibility_score:.0f}/100). "
                    "This location is well-positioned for distribution centers, container "
                    "storage, and cross-docking operations.",
                ])

        return "\n".join(lines)

    def generate_logistics_feasibility_matrix(self, land: Dict) -> str:
        """
        Generate the Logistics Feasibility Matrix for RAG output.

        This is the structured matrix that gets injected when an investor
        filters for Logistics/Warehouse usage. It covers Fuel, Maintenance,
        Rail, and Air Freight analysis in a compact tabular format.
        """
        analysis = self.analyze(land)
        land.get("logistics_meta", {})
        land_id = land["Land_ID"]
        region = f"{land['Governorate']} - {land['Region_City']}"
        usage = land.get("Allowed_Usage", "")

        lines = [
            f"LOGISTICS FEASIBILITY MATRIX -- {land_id} ({region})",
            f"Usage: {usage} | Accessibility Score: {analysis.accessibility_score:.0f}/100",
            "=" * 65,
            "",
            "  DIMENSION              | METRIC                          | VALUE",
            "  " + "-" * 63,
        ]

        # ── 1. Fleet Maintenance & Road Quality ──
        if analysis.fleet_maintenance:
            fm = analysis.fleet_maintenance
            lines.append(
                f"  Fleet Maintenance      | Road Quality Index              | {fm.road_quality_index.value}"
            )
            lines.append(
                f"  Fleet Maintenance      | Maintenance Overhead            | +{fm.maintenance_overhead_pct:.0f}%"
            )
            if fm.estimated_annual_maintenance_egp is not None:
                lines.append(
                    f"  Fleet Maintenance      | Annual Cost ({_REFERENCE_FLEET_SIZE} trucks)         | "
                    f"{fm.estimated_annual_maintenance_egp:>10,.0f} EGP"
                )
        else:
            lines.append("  Fleet Maintenance      | Road Quality Index              | N/A")

        # ── 2. Fuel Consumption Engine ──
        if analysis.fuel_trip:
            ft = analysis.fuel_trip
            lines.append(
                f"  Fuel Consumption       | Fuel Type                       | {ft.fuel_type.value}"
            )
            lines.append(
                f"  Fuel Consumption       | Distance to Port               | {ft.distance_km:.0f} km"
            )
            lines.append(
                f"  Fuel Consumption       | Consumption (one-way)           | {ft.consumption_liters:.1f} L"
            )
            lines.append(
                f"  Fuel Consumption       | Cost per Round-Trip             | {ft.cost_per_trip_egp:,.0f} EGP"
            )
            lines.append(
                f"  Fuel Consumption       | Cost per Ton-km                 | {ft.cost_per_ton_km_egp:.2f} EGP"
            )
            lines.append(
                f"  Fuel Consumption       | Solar Savings Potential         | {ft.solar_savings_pct:.1f}%"
            )
            lines.append(
                f"  Fuel Consumption       | Annual Fuel Cost                | {ft.annual_fuel_cost_egp:,.0f} EGP"
            )
        else:
            fuel = analysis.estimated_fuel_cost_per_trip_egp
            if fuel is not None:
                lines.append(
                    f"  Fuel Consumption       | Cost per Port Trip             | {fuel:,.0f} EGP"
                )

        # ── 3. Air Freight Connectivity ──
        if analysis.air_freight:
            af = analysis.air_freight
            lines.append(
                f"  Air Freight            | Nearest Cargo Airport           | {af.nearest_cargo_airport or 'N/A'}"
            )
            lines.append(
                f"  Air Freight            | Airport Tier                    | {af.airport_tier.value}"
            )
            lines.append(
                f"  Air Freight            | Trucking Transit Time           | {af.trucking_transit_hours:.1f} hours"
            )
            cap = f"{af.daily_cargo_capacity_tons:,.0f} tons" if af.daily_cargo_capacity_tons else "N/A"
            lines.append(
                f"  Air Freight            | Daily Cargo Capacity            | {cap}"
            )
            lines.append(
                f"  Air Freight            | Perishable Export               | "
                f"{'Yes' if af.perishable_export_suitable else 'No'}"
            )
        else:
            lines.append("  Air Freight            | Nearest Cargo Airport           | N/A")

        # ── 4. Rail Freight Integration ──
        if analysis.rail_freight:
            rf = analysis.rail_freight
            lines.append(
                f"  Rail Freight           | Rail Access                     | {'Yes' if rf.rail_access else 'No'}"
            )
            lines.append(
                f"  Rail Freight           | Network Type                    | {rf.network_type.value}"
            )
            if rf.station_name:
                lines.append(
                    f"  Rail Freight           | Station / Distance              | "
                    f"{rf.station_name} ({rf.station_distance_km:.0f} km)"
                    if rf.station_distance_km else f"  Rail Freight           | Station                         | {rf.station_name}"
                )
            lines.append(
                f"  Rail Freight           | Tonnage Cost Saving             | {rf.estimated_tonnage_cost_saving_pct:.0f}%"
            )
            lines.append(
                f"  Rail Freight           | Heavy-Tonnage Viable            | "
                f"{'Yes' if rf.heavy_tonnage_viable else 'No'}"
            )
        else:
            lines.append(
                f"  Rail Freight           | Rail Access                     | "
                f"{'Yes' if analysis.rail_freight_access else 'No'}"
            )

        # ── 5. Warehousing Infrastructure ──
        lines.append("  " + "-" * 63)
        lines.append(
            f"  Warehousing            | Container Handling              | "
            f"{'Yes' if analysis.container_handling_nearby else 'No'}"
        )
        lines.append(
            f"  Warehousing            | Cold Chain Available             | "
            f"{'Yes' if analysis.cold_chain_available else 'No'}"
        )
        if analysis.avg_truck_turnaround_hours is not None:
            lines.append(
                f"  Warehousing            | Truck Turnaround                | "
                f"{analysis.avg_truck_turnaround_hours:.1f} hours"
            )

        lines.extend(["", f"  OVERALL VERDICT: {analysis.logistics_verdict}"])

        return "\n".join(lines)

    def format_logistics_for_llm(self, land: Dict) -> str:
        """Compact logistics summary for appending to LLM context."""
        analysis = self.analyze(land)
        if analysis.accessibility_score == 0.0 and not analysis.rail_freight_access:
            return ""

        parts = [
            f"  Logistics Score: {analysis.accessibility_score:.0f}/100",
            f"  Highway: {analysis.nearest_highway_km:.1f}km | "
            f"Road: {analysis.road_quality.value} | "
            f"Rail: {'Yes' if analysis.rail_freight_access else 'No'}",
        ]

        # Fleet maintenance signal
        if analysis.fleet_maintenance and analysis.fleet_maintenance.maintenance_overhead_pct > 0:
            parts.append(
                f"  Fleet Maint Overhead: +{analysis.fleet_maintenance.maintenance_overhead_pct:.0f}%"
            )

        if analysis.fuel_trip and analysis.fuel_trip.annual_fuel_cost_egp > 0:
            parts.append(
                f"  Annual Fuel: {analysis.fuel_trip.annual_fuel_cost_egp:,.0f} EGP | "
                f"Per Ton-km: {analysis.fuel_trip.cost_per_ton_km_egp:.2f} EGP"
            )
        elif analysis.estimated_fuel_cost_per_trip_egp:
            parts.append(
                f"  Port Trip Fuel: {analysis.estimated_fuel_cost_per_trip_egp:,.0f} EGP | "
                f"Turnaround: {analysis.avg_truck_turnaround_hours or 'N/A'}h"
            )

        # Air freight signal
        if analysis.air_freight and analysis.air_freight.nearest_cargo_airport:
            af = analysis.air_freight
            parts.append(
                f"  Air Cargo: {af.nearest_cargo_airport} ({af.airport_tier.value}, "
                f"{af.trucking_transit_hours:.1f}h transit)"
            )

        # Rail freight signal
        if analysis.rail_freight and analysis.rail_freight.rail_access:
            rf = analysis.rail_freight
            parts.append(
                f"  Rail: {rf.network_type.value} at {rf.station_name} "
                f"(-{rf.estimated_tonnage_cost_saving_pct:.0f}% vs truck)"
            )

        if analysis.container_handling_nearby:
            parts.append("  Container terminal nearby")
        if analysis.cold_chain_available:
            parts.append("  Cold chain infrastructure available")

        parts.append(f"  Verdict: {analysis.logistics_verdict}")
        return "\n".join(parts)

    # ────────────────────────────────────────────────────────
    # Internal computation engines
    # ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_fleet_maintenance(
        road_quality: RoadQuality,
        land: Dict,
    ) -> FleetMaintenanceImpact:
        """
        Compute fleet maintenance impact based on Road Quality Index.

        Calculates the percentage increase in vehicle maintenance costs
        relative to an Excellent-road baseline, using Egyptian transport
        authority benchmark data for heavy-truck fleets operating on
        each road quality class.
        """
        overhead_pct = _FLEET_MAINTENANCE_OVERHEAD.get(road_quality, 28.0)
        wear_factors = _ROAD_WEAR_FACTORS.get(road_quality, ["Standard wear factors"])

        # Annual maintenance for reference fleet
        multiplier = 1.0 + (overhead_pct / 100.0)
        annual_cost = round(
            _BASELINE_ANNUAL_MAINT_PER_TRUCK_EGP * _REFERENCE_FLEET_SIZE * multiplier
        )

        return FleetMaintenanceImpact(
            road_quality_index=road_quality,
            maintenance_overhead_pct=overhead_pct,
            estimated_annual_maintenance_egp=annual_cost,
            wear_factors=wear_factors,
        )

    @staticmethod
    def _compute_fuel_consumption(
        raw: Dict,
        road_quality: RoadQuality,
        land: Dict,
    ) -> FuelTripEstimate:
        """
        Fuel Consumption Engine: Estimates fuel (Diesel/Solar) consumption
        and cost per trip from the land parcel to the nearest major
        Egyptian port or trade hub.

        Uses distance-based calculation with road quality degradation
        factors and current local fuel economics (Egyptian diesel pricing).
        """
        # Determine distance to the reference port
        port_km = raw.get("nearest_port_km_override")
        if port_km is None:
            port_km = raw.get("nearest_port_km_ref")
        if port_km is None:
            port_km = land.get("Nearest_Port_km")
        if port_km is None:
            return FuelTripEstimate()

        # Road quality degrades fuel efficiency
        road_factor = _ROAD_QUALITY_SCORES.get(road_quality, 0.65)
        # Poor roads increase consumption: consumption = base / road_factor
        # (road_factor < 1.0 means worse roads = more fuel per km)
        degradation = 1.0 + (1.0 - road_factor) * 0.30  # up to +30% extra for Unpaved

        # Determine fuel type: Solar-assisted if the land has high solar potential
        # (desert areas with high electricity capacity or solar-hybrid grid)
        fuel_type = FuelType.DIESEL
        solar_savings = 0.0
        electricity_grid = land.get("Electricity_Grid_Type", "")
        if "solar" in electricity_grid.lower() or "hybrid" in electricity_grid.lower():
            fuel_type = FuelType.HYBRID
            solar_savings = _SOLAR_SAVINGS_PCT
        elif land.get("Electricity_Capacity_MW", 0) >= 50:
            fuel_type = FuelType.HYBRID
            solar_savings = _SOLAR_SAVINGS_PCT

        # Base consumption for the chosen fuel type
        if fuel_type == FuelType.HYBRID:
            base_liters_per_km = _SOLAR_DIESEL_LITERS_PER_KM
        else:
            base_liters_per_km = _DIESEL_LITERS_PER_KM

        # One-way consumption
        one_way_liters = base_liters_per_km * port_km * degradation
        # Round-trip consumption
        round_trip_liters = one_way_liters * 2.0

        # Cost calculation
        cost_per_trip = round_trip_liters * _DIESEL_PRICE_PER_LITER_EGP

        # Per ton-km (round trip, reference payload)
        ton_km = port_km * 2 * _REFERENCE_TRUCK_PAYLOAD_TONS
        cost_per_ton_km = cost_per_trip / ton_km if ton_km > 0 else 0.0

        # Annual projection
        annual_fuel_cost = cost_per_trip * _ANNUAL_TRIP_DAYS

        return FuelTripEstimate(
            fuel_type=fuel_type,
            distance_km=port_km,
            consumption_liters=round(one_way_liters, 1),
            cost_per_trip_egp=round(cost_per_trip),
            cost_per_ton_km_egp=round(cost_per_ton_km, 2),
            solar_savings_pct=solar_savings,
            annual_fuel_cost_egp=round(annual_fuel_cost),
        )

    @staticmethod
    def _compute_air_freight_connectivity(raw: Dict) -> AirFreightConnectivity:
        """
        Map the land to the nearest valid cargo-enabled airport and
        calculate trucking transit times for last-mile cargo movement.

        Recognized cargo-enabled Egyptian airports:
          - Cairo International Airport (Tier-1 Major)
          - Sphinx International Airport (Tier-2 Regional)
          - Borg El Arab Airport (Tier-2 Regional)
          - Aswan International Airport (Tier-2 Regional)
        """
        airport_name = raw.get("nearest_cargo_airport_name", "")
        distance_km = raw.get("nearest_cargo_airport_km")

        # Look up airport registry for structured data
        registry_entry = _CARGO_AIRPORT_REGISTRY.get(airport_name, {})

        tier = raw.get("cargo_airport_tier", "None")
        try:
            airport_tier = CargoAirportTier(tier)
        except ValueError:
            airport_tier = registry_entry.get("tier", CargoAirportTier.NONE)

        daily_capacity = raw.get("cargo_airport_daily_capacity_tons")
        if daily_capacity is None:
            daily_capacity = registry_entry.get("daily_capacity_tons")

        perishable = raw.get("cargo_airport_perishable_export")
        if perishable is None:
            perishable = registry_entry.get("perishable_export", False)

        # Calculate trucking transit time
        # Average truck speed: 60 km/h on paved roads, 35 km/h on poor/unpaved
        road_quality = raw.get("road_quality", "Average")
        avg_speed_kmh = 40.0  # conservative default for cargo trucks
        if road_quality in ("Excellent", "Good"):
            avg_speed_kmh = 55.0
        elif road_quality == "Average":
            avg_speed_kmh = 45.0
        elif road_quality in ("Poor", "Unpaved"):
            avg_speed_kmh = 30.0

        transit_hours = (distance_km / avg_speed_kmh) if distance_km and distance_km > 0 else 0.0

        return AirFreightConnectivity(
            nearest_cargo_airport=airport_name,
            airport_tier=airport_tier,
            distance_km=distance_km or 0.0,
            trucking_transit_hours=round(transit_hours, 1),
            daily_cargo_capacity_tons=daily_capacity,
            perishable_export_suitable=bool(perishable),
        )

    @staticmethod
    def _compute_rail_freight(raw: Dict) -> RailFreightIntegration:
        """
        Compute rail freight integration analysis.

        Determines access to Egyptian National Railways freight lines
        or the new High-Speed Electric Rail Cargo network, and
        estimates heavy-tonnage transportation cost savings.
        """
        rail_access = raw.get("rail_freight_access", False)

        network_str = raw.get("rail_network_type", "None")
        try:
            network_type = RailNetworkType(network_str)
        except ValueError:
            network_type = RailNetworkType.NONE

        station_name = raw.get("rail_station_name", "")
        station_distance = raw.get("rail_station_distance_km")

        # Cost saving percentage
        cost_saving = raw.get("rail_cost_saving_pct")
        if cost_saving is None:
            cost_saving = _RAIL_COST_SAVINGS.get(network_type, 0.0)

        # Heavy-tonnage viability: High-Speed Electric always viable when connected,
        # Conventional Freight viable if cost saving >= 20%
        heavy_tonnage = raw.get("rail_heavy_tonnage_viable", False)
        if not heavy_tonnage and rail_access:
            if network_type == RailNetworkType.HIGH_SPEED_ELECTRIC:
                heavy_tonnage = True
            elif network_type == RailNetworkType.CONVENTIONAL_FREIGHT and cost_saving >= 20.0:
                heavy_tonnage = True

        return RailFreightIntegration(
            rail_access=rail_access,
            network_type=network_type,
            station_name=station_name,
            station_distance_km=station_distance,
            estimated_tonnage_cost_saving_pct=cost_saving,
            heavy_tonnage_viable=heavy_tonnage,
        )

    def _compute_accessibility(self, raw: Dict, road_quality: RoadQuality) -> float:
        """
        Compute composite logistics accessibility score (0-100).

        Weights: Highway 30, Road Quality 20, Port 25, Rail 15, Cargo Airport 10.
        """
        score = 0.0

        # ── Highway proximity (0-30) ──
        hw_km = raw.get("nearest_highway_km")
        if hw_km is not None:
            hw_score = max(0.0, 1.0 - (hw_km / _HW_MAX_KM))
            score += hw_score * 30.0

        # ── Road quality (0-20) ──
        rq_score = _ROAD_QUALITY_SCORES.get(road_quality, 0.5)
        score += rq_score * 20.0

        # ── Port access (0-25) ──
        port_km = raw.get("nearest_port_km_override")
        if port_km is None:
            port_km = raw.get("nearest_port_km_ref")
        if port_km is not None:
            port_score = max(0.0, 1.0 - (port_km / _PORT_MAX_KM))
            score += port_score * 25.0

        # ── Rail freight (0-15) ──
        if raw.get("rail_freight_access", False):
            score += 15.0

        # ── Cargo airport (0-10) ──
        cargo_km = raw.get("nearest_cargo_airport_km")
        if cargo_km is not None:
            air_score = max(0.0, 1.0 - (cargo_km / _CARGO_AIRPORT_MAX_KM))
            score += air_score * 10.0

        # ── Bonus: container handling (+3) ──
        if raw.get("container_handling_nearby", False):
            score = min(score + 3.0, 100.0)

        # ── Bonus: cold chain (+2) ──
        if raw.get("cold_chain_available", False):
            score = min(score + 2.0, 100.0)

        return round(score, 1)

    @staticmethod
    def _generate_verdict(accessibility: float, raw: Dict, land: Dict) -> str:
        """Generate one-line logistics verdict."""
        usage = land.get("Allowed_Usage", "")

        if accessibility >= 75:
            verdict = (
                "Prime logistics hub location with excellent multimodal connectivity. "
                "Ideal for distribution centers and bonded warehousing."
            )
        elif accessibility >= 55:
            verdict = (
                "Strong logistics accessibility with good highway and port connections. "
                "Suitable for most warehousing and freight operations."
            )
        elif accessibility >= 35:
            verdict = (
                "Moderate logistics access. Functional for regional distribution "
                "but may incur higher per-unit transportation costs."
            )
        elif accessibility >= 20:
            verdict = (
                "Limited logistics infrastructure. Road or rail upgrades "
                "may be needed for commercial-scale freight operations."
            )
        else:
            verdict = (
                "Poor logistics accessibility. Significant investment in "
                "transportation links required before viable for logistics use."
            )

        if usage == "Logistics" and accessibility < 40:
            verdict += " Current logistics zoning may not offset the accessibility deficit."
        elif usage == "Agricultural" and accessibility < 30:
            verdict += " For agricultural use, moderate access is acceptable -- proximity to markets is secondary to water/soil."

        return verdict

    @staticmethod
    def _extract_highlights(analysis: LogisticsMeta, raw: Dict, land: Dict) -> List[str]:
        """Extract 2-4 key logistics highlights for ranking display."""
        highlights = []

        if analysis.nearest_highway_km is not None and analysis.nearest_highway_km <= 3:
            highlights.append(f"Highway access within {analysis.nearest_highway_km:.0f}km")

        if analysis.rail_freight_access:
            highlights.append(f"Rail freight at {analysis.rail_station_name or 'nearby station'}")
            if analysis.rail_freight:
                rf = analysis.rail_freight
                if rf.network_type == RailNetworkType.HIGH_SPEED_ELECTRIC:
                    highlights.append(f"High-Speed Electric Rail (-{rf.estimated_tonnage_cost_saving_pct:.0f}% cost)")
                elif rf.heavy_tonnage_viable:
                    highlights.append(f"Rail heavy-tonnage viable (-{rf.estimated_tonnage_cost_saving_pct:.0f}% cost)")

        if analysis.fuel_trip:
            ft = analysis.fuel_trip
            if ft.cost_per_ton_km_egp <= 0.30:
                highlights.append(f"Low fuel cost: {ft.cost_per_ton_km_egp:.2f} EGP/ton-km")
            elif ft.cost_per_ton_km_egp >= 1.00:
                highlights.append(f"High fuel cost: {ft.cost_per_ton_km_egp:.2f} EGP/ton-km")
            if ft.solar_savings_pct > 0:
                highlights.append(f"Solar-assisted fleet saves {ft.solar_savings_pct:.1f}%")
        elif analysis.estimated_fuel_cost_per_trip_egp is not None:
            if analysis.estimated_fuel_cost_per_trip_egp <= 1500:
                highlights.append(f"Low fuel cost: {analysis.estimated_fuel_cost_per_trip_egp:,.0f} EGP/trip to port")
            elif analysis.estimated_fuel_cost_per_trip_egp >= 4000:
                highlights.append(f"High fuel cost: {analysis.estimated_fuel_cost_per_trip_egp:,.0f} EGP/trip to port")

        if analysis.air_freight and analysis.air_freight.nearest_cargo_airport:
            af = analysis.air_freight
            if af.airport_tier == CargoAirportTier.TIER_1_MAJOR:
                highlights.append(f"Tier-1 cargo airport: {af.nearest_cargo_airport}")
            if af.trucking_transit_hours <= 1.0:
                highlights.append("Under 1h to cargo airport")

        if analysis.container_handling_nearby:
            highlights.append("Container terminal nearby")

        if analysis.cold_chain_available:
            highlights.append("Cold chain support")

        port_km = land.get("Nearest_Port_km")
        if port_km is not None and port_km <= 10:
            highlights.append(f"Only {port_km:.0f}km from seaport")

        if analysis.fleet_maintenance and analysis.fleet_maintenance.maintenance_overhead_pct == 0:
            highlights.append("Excellent roads - zero fleet maintenance overhead")

        if not highlights:
            highlights.append("Standard logistics infrastructure")

        return highlights[:5]