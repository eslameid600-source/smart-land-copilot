"""
Smart Land Management Copilot — ETL Service
==============================================
Designed for extracting data from Egyptian government sources
(NUCA, GAFI, Ministry of Agriculture, Geological Survey).
Supports CSV, Excel, and API-based data ingestion.
"""

import csv
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class ETLService:
    """
    Extract-Transform-Load service for integrating external data sources.
    Currently supports CSV/Excel file ingestion with data validation
    and normalization. API connectors are stubbed for production expansion.
    """

    REQUIRED_FIELDS = [
        "Land_ID", "Governorate", "Region_City",
        "Latitude", "Longitude", "Total_Area_Sqm",
        "Price_Per_Sqm_EGP", "Allowed_Usage",
    ]

    OPTIONAL_FIELDS = [
        "Soil_Mineral_Type", "Nearest_Highways", "Utilities_Availability",
        "Gov_Feasibility_Notes", "Investment_Status", "Auction_Date",
        "Starting_Price_Per_Sqm_EGP",
        # Extended fields
        "Bearing_Capacity_kPa", "Groundwater_Depth_m", "Seismic_Risk",
        "Liquefaction_Risk", "Subsidence_Risk", "Water_Quality",
        "pH_Level", "Environmental_Permit_Required", "Flood_Risk",
        "Electricity_Capacity_MW", "Gas_Pipeline", "Fiber_Optic",
        "Sewage_Connection", "Internet_Speed_Mbps",
        "Nearest_Airport_km", "Nearest_Port_km",
        "Historical_Price_1Y_Ago", "Market_Trend",
        "Development_Cost_Per_Sqm",
    ]

    def __init__(self):
        self._ingestion_log: List[Dict] = []

    def ingest_csv(
        self,
        file_path: str,
        source_name: str = "CSV Upload",
    ) -> Dict:
        """
        Ingest land records from a CSV file.

        Returns a dict with:
          - records: list of validated land dicts
          - errors: list of validation error messages
          - stats: ingestion statistics
        """
        records = []
        errors = []
        total_rows = 0

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):
                    total_rows += 1
                    try:
                        validated = self._validate_and_normalize(row)
                        records.append(validated)
                    except ValueError as e:
                        errors.append(f"Row {row_num}: {e}")
        except FileNotFoundError:
            errors.append(f"File not found: {file_path}")
        except Exception as e:
            errors.append(f"Failed to read CSV: {e}")

        stats = {
            "source": source_name,
            "file": os.path.basename(file_path),
            "total_rows": total_rows,
            "successful": len(records),
            "failed": len(errors),
            "timestamp": datetime.now().isoformat(),
        }
        self._ingestion_log.append(stats)
        logger.info(f"ETL ingestion: {stats}")

        return {"records": records, "errors": errors, "stats": stats}

    def ingest_excel(
        self,
        file_path: str,
        source_name: str = "Excel Upload",
        sheet_name: Optional[str] = None,
    ) -> Dict:
        """Ingest land records from an Excel file."""
        try:
            import pandas as pd
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            else:
                df = pd.read_excel(file_path)

            records = []
            errors = []
            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                # Convert NaN to None
                row_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
                try:
                    validated = self._validate_and_normalize(row_dict)
                    records.append(validated)
                except ValueError as e:
                    errors.append(f"Row {idx + 2}: {e}")

            stats = {
                "source": source_name,
                "file": os.path.basename(file_path),
                "total_rows": len(df),
                "successful": len(records),
                "failed": len(errors),
                "timestamp": datetime.now().isoformat(),
            }
            self._ingestion_log.append(stats)
            return {"records": records, "errors": errors, "stats": stats}

        except ImportError:
            return {
                "records": [], "errors": ["openpyxl not installed. Run: pip install openpyxl"],
                "stats": {"source": source_name, "successful": 0, "failed": 0},
            }
        except Exception as e:
            return {
                "records": [], "errors": [f"Failed to read Excel: {e}"],
                "stats": {"source": source_name, "successful": 0, "failed": 1},
            }

    def ingest_json(self, json_data: str, source_name: str = "JSON") -> Dict:
        """Ingest from a JSON string (array of objects)."""
        try:
            items = json.loads(json_data)
            if not isinstance(items, list):
                items = [items]

            records = []
            errors = []
            for i, item in enumerate(items):
                try:
                    validated = self._validate_and_normalize(item)
                    records.append(validated)
                except ValueError as e:
                    errors.append(f"Item {i + 1}: {e}")

            stats = {
                "source": source_name,
                "total_rows": len(items),
                "successful": len(records),
                "failed": len(errors),
                "timestamp": datetime.now().isoformat(),
            }
            self._ingestion_log.append(stats)
            return {"records": records, "errors": errors, "stats": stats}
        except json.JSONDecodeError as e:
            return {
                "records": [], "errors": [f"Invalid JSON: {e}"],
                "stats": {"source": source_name, "successful": 0, "failed": 0},
            }

    def get_ingestion_history(self) -> List[Dict]:
        return self._ingestion_log

    def _validate_and_normalize(self, raw: Dict) -> Dict:
        """Validate and normalize a single record."""
        # Check required fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in raw or raw[f] is None]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        record = {}

        # Numeric fields with conversion
        record["Land_ID"] = str(raw["Land_ID"]).strip()
        record["Governorate"] = str(raw["Governorate"]).strip()
        record["Region_City"] = str(raw["Region_City"]).strip()
        record["Latitude"] = float(raw["Latitude"])
        record["Longitude"] = float(raw["Longitude"])
        record["Total_Area_Sqm"] = int(float(raw["Total_Area_Sqm"]))
        record["Price_Per_Sqm_EGP"] = float(raw["Price_Per_Sqm_EGP"])

        # Validate coordinates (Egypt bounds)
        if not (21.0 <= record["Latitude"] <= 32.0):
            raise ValueError(f"Latitude {record['Latitude']} outside Egypt bounds (21-32)")
        if not (24.0 <= record["Longitude"] <= 36.0):
            raise ValueError(f"Longitude {record['Longitude']} outside Egypt bounds (24-36)")
        if record["Total_Area_Sqm"] <= 0:
            raise ValueError("Total area must be positive")
        if record["Price_Per_Sqm_EGP"] <= 0:
            raise ValueError("Price per sqm must be positive")

        record["Allowed_Usage"] = str(raw.get("Allowed_Usage", "Industrial")).strip()

        # String fields with defaults
        record["Soil_Mineral_Type"] = str(raw.get("Soil_Mineral_Type", "Not specified")).strip()
        record["Nearest_Highways"] = str(raw.get("Nearest_Highways", "Not specified")).strip()
        record["Utilities_Availability"] = str(raw.get("Utilities_Availability", "")).strip()
        record["Gov_Feasibility_Notes"] = str(raw.get("Gov_Feasibility_Notes", "")).strip()

        # Optional fields
        record["Investment_Status"] = str(raw.get("Investment_Status", "Direct Sale")).strip()
        record["Auction_Date"] = raw.get("Auction_Date")
        record["Starting_Price_Per_Sqm_EGP"] = (
            float(raw["Starting_Price_Per_Sqm_EGP"])
            if raw.get("Starting_Price_Per_Sqm_EGP") else None
        )

        # Extended fields (pass through if present)
        for field in self.OPTIONAL_FIELDS:
            if field in raw and field not in record:
                val = raw[field]
                if val is None or (isinstance(val, float) and val != val):  # NaN check
                    record[field] = None
                elif field.endswith("_km") or field.endswith("_m") or field.endswith("_MW") or field.endswith("_m3") or field.endswith("_kPa"):
                    record[field] = float(val) if val is not None else None
                elif field.endswith("_Pct"):
                    record[field] = float(val) if val is not None else None
                elif field in ("Liquefaction_Risk", "Subsidence_Risk", "Environmental_Permit_Required",
                               "Gas_Pipeline", "Fiber_Optic", "Sewage_Connection", "Railway_Access"):
                    record[field] = bool(val) if val is not None else False
                elif field == "Internet_Speed_Mbps":
                    record[field] = int(float(val)) if val is not None else None
                else:
                    record[field] = str(val).strip() if val is not None else None

        return record