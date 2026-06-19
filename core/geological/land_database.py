"""
============================================================
Smart Land Management Copilot — Land Database (Raw Data)
============================================================
Single source of truth for all land records.
Pure data module — no business logic here.

Each record includes:
  - Latitude / Longitude  : Separate float fields for Folium
  - Radius                : Approximate circle radius in meters (computed)
  - Investment_Status     : "Direct Sale" or "Public Auction"
  - Auction_Date          : Date string (only for auction lands)
  - Starting_Price_Per_Sqm_EGP : Auction starting price (only for auction lands)
============================================================
"""

from __future__ import annotations

from typing import Any, Dict, List


# ----------------------------------------------------------
# RAW DATASET — Python dicts for easy serialization
# ----------------------------------------------------------
LANDS_RAW: List[Dict[str, Any]] = [
    {
        "Land_ID": "EG-CAI-01",
        "Governorate": "Cairo",
        "Region_City": "New Cairo",
        "Latitude": 30.0074,
        "Longitude": 31.4070,
        "Total_Area_Sqm": 50_000,
        "Price_Per_Sqm_EGP": 12_500,
        "Soil_Mineral_Type": "Sandy limestone",
        "Allowed_Usage": "Residential",
        "Nearest_Highways": "Ring Road, Sokhna Road",
        "Utilities_Availability": "Water, Electricity, Gas, Fiber-Optic",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "Prime residential plot near American University in Cairo. "
            "High demand, proximity to New Administrative Capital enhances value. "
            "All utilities available. Zoning: R-3 mixed-use residential."
        ),
    },
    {
        "Land_ID": "EG-CAI-02",
        "Governorate": "Cairo",
        "Region_City": "New Administrative Capital",
        "Latitude": 30.0094,
        "Longitude": 31.7536,
        "Total_Area_Sqm": 200_000,
        "Price_Per_Sqm_EGP": 8_200,
        "Soil_Mineral_Type": "Sandy clay",
        "Allowed_Usage": "Residential",
        "Nearest_Highways": "Regional Ring Road, Cairo-Suez Road",
        "Utilities_Availability": "Water, Electricity, Gas, Fiber-Optic",
        "Investment_Status": "Public Auction",
        "Auction_Date": "2026-08-15",
        "Starting_Price_Per_Sqm_EGP": 7_500,
        "Gov_Feasibility_Notes": (
            "Government district adjacent. Strategic location for residential compounds. "
            "Infrastructure fully installed by ACUD. "
            "Zoning: R-2 high-density residential with commercial ground floor allowance."
        ),
    },
    {
        "Land_ID": "EG-SHQ-01",
        "Governorate": "Sharqia",
        "Region_City": "10th of Ramadan",
        "Latitude": 30.3069,
        "Longitude": 31.7440,
        "Total_Area_Sqm": 150_000,
        "Price_Per_Sqm_EGP": 3_800,
        "Soil_Mineral_Type": "Sandy",
        "Allowed_Usage": "Industrial",
        "Nearest_Highways": "Cairo-Ismailia Desert Road, Regional Ring Road",
        "Utilities_Availability": "Water, Electricity, Gas",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "Established industrial city. Proximity to Cairo and Port Said via desert road. "
            "Gas pipeline available, limited fiber-optic in older sectors. "
            "Home to >1,200 factories. Zoning: I-2 heavy/light industrial."
        ),
    },
    {
        "Land_ID": "EG-MNF-01",
        "Governorate": "Monufia",
        "Region_City": "Sadat City",
        "Latitude": 30.3667,
        "Longitude": 30.5333,
        "Total_Area_Sqm": 120_000,
        "Price_Per_Sqm_EGP": 1_900,
        "Soil_Mineral_Type": "Limestone and clay",
        "Allowed_Usage": "Logistics",
        "Nearest_Highways": "Cairo-Alexandria Desert Road",
        "Utilities_Availability": "Water, Electricity, Gas",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "Logistics hub on Cairo-Alex corridor. Dry port planned by Ministry of Transport. "
            "Groundwater well supply; electricity grid stable. "
            "Zoning: L-1 logistics and warehousing with bonded-area potential."
        ),
    },
    {
        "Land_ID": "EG-ALX-01",
        "Governorate": "Alexandria",
        "Region_City": "Borg El Arab",
        "Latitude": 30.9167,
        "Longitude": 29.5333,
        "Total_Area_Sqm": 80_000,
        "Price_Per_Sqm_EGP": 4_500,
        "Soil_Mineral_Type": "Limestone",
        "Allowed_Usage": "Industrial",
        "Nearest_Highways": "Cairo-Alexandria Desert Road, Borg El Arab Airport Road",
        "Utilities_Availability": "Water, Electricity, Gas, Fiber-Optic",
        "Investment_Status": "Public Auction",
        "Auction_Date": "2026-09-20",
        "Starting_Price_Per_Sqm_EGP": 3_800,
        "Gov_Feasibility_Notes": (
            "Close to Alexandria port and airport. Ideal for export-oriented industries. "
            "Fiber-optic backbone connects to submarine cables. "
            "Zoning: I-1 industrial with port-back corridor designation."
        ),
    },
    {
        "Land_ID": "EG-SUE-01",
        "Governorate": "Suez",
        "Region_City": "Sokhna (SCZone)",
        "Latitude": 29.6182,
        "Longitude": 32.3185,
        "Total_Area_Sqm": 250_000,
        "Price_Per_Sqm_EGP": 2_700,
        "Soil_Mineral_Type": "Sandy and rocky",
        "Allowed_Usage": "Logistics",
        "Nearest_Highways": "Sokhna Road, Cairo-Suez Road",
        "Utilities_Availability": "Water, Electricity, Gas, Fiber-Optic",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "SCZone land adjacent to Sokhna Port. Excellent for logistics and warehousing. "
            "Direct access to Suez Canal. Full utilities by TEDA. "
            "Tax incentives under Investment Law No. 72/2017. Zoning: L-2 free-zone logistics."
        ),
    },
    {
        "Land_ID": "EG-DAM-01",
        "Governorate": "Damietta",
        "Region_City": "Damietta Port Area",
        "Latitude": 31.4167,
        "Longitude": 31.8167,
        "Total_Area_Sqm": 100_000,
        "Price_Per_Sqm_EGP": 3_200,
        "Soil_Mineral_Type": "Alluvial clay",
        "Allowed_Usage": "Logistics",
        "Nearest_Highways": "Damietta-Port Said International Road",
        "Utilities_Availability": "Water, Electricity, Gas",
        "Investment_Status": "Public Auction",
        "Auction_Date": "2026-07-10",
        "Starting_Price_Per_Sqm_EGP": 2_800,
        "Gov_Feasibility_Notes": (
            "Proximity to Damietta Port, container terminal. Suitable for grain and fertilizer logistics. "
            "Gas from national grid, water from Nile branch. "
            "Zoning: L-1 logistics near port authority jurisdiction."
        ),
    },
    {
        "Land_ID": "EG-ISM-01",
        "Governorate": "Ismailia",
        "Region_City": "Ismailia (East of Canal)",
        "Latitude": 30.5965,
        "Longitude": 32.2715,
        "Total_Area_Sqm": 90_000,
        "Price_Per_Sqm_EGP": 1_500,
        "Soil_Mineral_Type": "Sandy and fertile",
        "Allowed_Usage": "Agricultural",
        "Nearest_Highways": "Ismailia-Port Said Road, Suez Canal Tunnel Road",
        "Utilities_Availability": "Water, Electricity",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "Agricultural plot near El-Salam Canal, reliable irrigation. "
            "Electricity available, no gas pipeline currently. "
            "Suitable for citrus and vegetables export. Zoning: A-1 irrigated agriculture."
        ),
    },
    {
        "Land_ID": "EG-ASW-01",
        "Governorate": "Aswan",
        "Region_City": "Toshka",
        "Latitude": 22.5833,
        "Longitude": 31.2833,
        "Total_Area_Sqm": 500_000,
        "Price_Per_Sqm_EGP": 250,
        "Soil_Mineral_Type": "Sandy loam with phosphate deposits",
        "Allowed_Usage": "Agricultural",
        "Nearest_Highways": "Abu Simbel Road, Western Desert Road",
        "Utilities_Availability": "Water, Electricity",
        "Investment_Status": "Public Auction",
        "Auction_Date": "2026-10-05",
        "Starting_Price_Per_Sqm_EGP": 200,
        "Gov_Feasibility_Notes": (
            "Part of Toshka reclamation project. Groundwater from Nubian aquifer, "
            "solar-powered pumps feasible. Phosphate residues may require treatment for certain crops. "
            "Federal subsidy for wheat farming under Toshka National Project. Zoning: A-2 reclaimed desert agriculture."
        ),
    },
    {
        "Land_ID": "EG-BEH-01",
        "Governorate": "Beheira",
        "Region_City": "Wadi El Natrun",
        "Latitude": 30.3333,
        "Longitude": 30.0333,
        "Total_Area_Sqm": 180_000,
        "Price_Per_Sqm_EGP": 850,
        "Soil_Mineral_Type": "Sandy and saline",
        "Allowed_Usage": "Agricultural",
        "Nearest_Highways": "Cairo-Alexandria Desert Road",
        "Utilities_Availability": "Water, Electricity",
        "Investment_Status": "Direct Sale",
        "Auction_Date": None,
        "Starting_Price_Per_Sqm_EGP": None,
        "Gov_Feasibility_Notes": (
            "Near Wadi El Natrun, saline-tolerant crops recommended (quinoa, date palms). "
            "Nile water available through El-Nasr Canal extension. "
            "Soil improvement needed; government offers land reclamation incentives. Zoning: A-2 reclaimed agriculture."
        ),
    },
]