import os
import csv
import uuid
import math
import logging
import hmac
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Flask, request, jsonify
from flask_cors import CORS

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter


# ============================================================
# 1. APPLICATION CONFIGURATION
# ============================================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# These files will contain imported source data.
# They are NOT hardcoded emission factors.
ACTIVITY_FACTORS_FILE = os.path.join(
    DATA_DIR,
    "activity_factors.csv"
)

GWP_VALUES_FILE = os.path.join(
    DATA_DIR,
    "gwp_values.csv"
)

CALCULATION_VERSION = "data-driven-v1"

EMISSIONS_UNIT = "tCO2e"

# Temporary single-reviewer gate for the backend MVP.
# Never hardcode these values or expose the token to the frontend.
MAPPING_REVIEW_TOKEN = os.environ.get(
    "MAPPING_REVIEW_TOKEN", ""
).strip()

MAPPING_REVIEWER_ID = os.environ.get(
    "MAPPING_REVIEWER_ID", ""
).strip()


# ============================================================
# 2. FIREBASE / FIRESTORE
# ============================================================

SERVICE_ACCOUNT_PATH = os.path.join(
    BASE_DIR,
    "carbon-audit-service-account.json"
)

if not firebase_admin._apps:
    if os.path.isfile(SERVICE_ACCOUNT_PATH):
        # Local development: use the ignored service-account JSON file.
        credentials_object = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(credentials_object)
    else:
        # Cloud Run: use Application Default Credentials from the service
        # identity attached to the service; do not ship a JSON key.
        firebase_admin.initialize_app()

db = firestore.client()


# ============================================================
# 3. INDUSTRY / PROCESS / ACTIVITY CATALOG
#
# These are application labels and suggested input units.
# They are NOT emission factors.
#
# A unit is usable for calculation only when the selected
# source dataset actually contains a matching factor.
# ============================================================

INDUSTRY_CATALOG = [
    {
        "id": "steel_manufacturing",
        "name": "Steel & Heavy Manufacturing",
        "processes": [
            {
                "id": "melting",
                "name": "Melting",
                "activities": [
                    {
                        "id": "coal_coke_consumption",
                        "name": "Coal / coke consumption",
                        "suggested_units": ["kg", "tonnes"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "natural_gas_consumption",
                        "name": "Natural gas consumption",
                        "suggested_units": ["kWh", "m3"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "casting",
                "name": "Casting",
                "activities": [
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "natural_gas_consumption",
                        "name": "Natural gas consumption",
                        "suggested_units": ["kWh", "m3"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "rolling_finishing",
                "name": "Rolling & Finishing",
                "activities": [
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "diesel_consumption",
                        "name": "Diesel consumption",
                        "suggested_units": ["litres"],
                        "calculation_type": "activity_factor"
                    }
                ]
            }
        ]
    },
    {
        "id": "logistics_freight",
        "name": "Logistics & Freight",
        "processes": [
            {
                "id": "road_freight",
                "name": "Road Freight",
                "activities": [
                    {
                        "id": "diesel_consumption",
                        "name": "Diesel consumption",
                        "suggested_units": ["litres"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "vehicle_distance",
                        "name": "Vehicle distance travelled",
                        "suggested_units": ["km"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "freight_transport_work",
                        "name": "Freight transport work",
                        "suggested_units": ["tonne_km"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "warehousing",
                "name": "Warehousing",
                "activities": [
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "natural_gas_consumption",
                        "name": "Natural gas consumption",
                        "suggested_units": ["kWh", "m3"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "refrigerated_transport",
                "name": "Refrigerated Transport",
                "activities": [
                    {
                        "id": "refrigerant_leakage",
                        "name": "Refrigerant leakage / refill",
                        "suggested_units": ["kg"],
                        "calculation_type": "activity_factor"
                    }
                ]
            }
        ]
    },
    {
        "id": "commercial_buildings",
        "name": "Commercial Buildings & Real Estate",
        "processes": [
            {
                "id": "space_heating",
                "name": "Space Heating",
                "activities": [
                    {
                        "id": "natural_gas_consumption",
                        "name": "Natural gas consumption",
                        "suggested_units": ["kWh", "m3"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "building_electricity",
                "name": "Building Electricity",
                "activities": [
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "building_refrigeration",
                "name": "HVAC & Refrigeration",
                "activities": [
                    {
                        "id": "refrigerant_leakage",
                        "name": "Refrigerant leakage / refill",
                        "suggested_units": ["kg"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    }
                ]
            }
        ]
    },
    {
        "id": "power_generation",
        "name": "Power Generation & Utilities",
        "processes": [
            {
                "id": "fuel_combustion",
                "name": "Fuel Combustion",
                "activities": [
                    {
                        "id": "natural_gas_consumption",
                        "name": "Natural gas consumption",
                        "suggested_units": ["m3"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "diesel_consumption",
                        "name": "Diesel consumption",
                        "suggested_units": ["litres"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "switchgear",
                "name": "Electrical Switchgear",
                "activities": [
                    {
                        "id": "sf6_leakage",
                        "name": "SF6 leakage / refill",
                        "suggested_units": ["kg"],
                        "calculation_type": "activity_factor"
                    }
                ]
            }
        ]
    },
    {
        "id": "agriculture_food",
        "name": "Agriculture & Food Production",
        "processes": [
            {
                "id": "livestock",
                "name": "Livestock",
                "activities": [
                    {
                        "id": "livestock_population",
                        "name": "Livestock population",
                        "suggested_units": ["head_year"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "fertilizer_application",
                "name": "Fertilizer Application",
                "activities": [
                    {
                        "id": "nitrogen_application",
                        "name": "Nitrogen applied",
                        "suggested_units": ["kg_N", "tonnes_N"],
                        "calculation_type": "activity_factor"
                    }
                ]
            },
            {
                "id": "farm_machinery",
                "name": "Farm Machinery",
                "activities": [
                    {
                        "id": "diesel_consumption",
                        "name": "Diesel consumption",
                        "suggested_units": ["litres"],
                        "calculation_type": "activity_factor"
                    },
                    {
                        "id": "electricity_consumption",
                        "name": "Electricity consumption",
                        "suggested_units": ["kWh", "MWh"],
                        "calculation_type": "activity_factor"
                    }
                ]
            }
        ]
    },
    {
        "id": "banking_financial_services",
        "name": "Banking & Financial Services",
        "processes": [
            {
                "id": "loans_investments",
                "name": "Loans & Investments",
                "activities": [
                    {
                        "id": "financed_emissions",
                        "name": "Financed emissions",
                        "suggested_units": [],
                        "calculation_type": "financed_emissions"
                    }
                ]
            }
        ]
    }
]


# ============================================================
# 4. METHODOLOGY / GWP / ACCOUNTING OPTIONS
#
# These are methodology identifiers and descriptions.
# No factor values or GWP numbers are stored here.
# Dataset availability comes from the imported files.
# ============================================================

FACTOR_SOURCES = [
    {
        "id": "defra_desnz",
        "name": "DEFRA / DESNZ Conversion Factors",
        "description": (
            "Annual UK government greenhouse gas reporting "
            "conversion factors."
        ),
        "url": (
            "https://www.gov.uk/government/collections/"
            "government-conversion-factors-for-company-reporting"
        )
    },
    {
        "id": "ipcc_2006",
        "name": "IPCC 2006 Guidelines",
        "description": (
            "IPCC inventory methods and applicable default factors."
        ),
        "url": (
            "https://www.ipcc-nggip.iges.or.jp/public/2006gl/"
        )
    },
    {
        "id": "ipcc_2019_refinement",
        "name": "IPCC 2019 Refinement",
        "description": (
            "Refinement used in conjunction with the 2006 IPCC "
            "Guidelines where applicable."
        ),
        "url": (
            "https://www.ipcc-nggip.iges.or.jp/public/2019rf/"
        )
    }
]

GWP_BASIS_OPTIONS = [
    {
        "id": "source_defined",
        "name": "As published by the selected factor source",
        "description": (
            "Use the CO2e basis defined by that source. "
            "It cannot be silently replaced with another GWP basis."
        )
    },
    {
        "id": "ipcc_ar5",
        "name": "IPCC Fifth Assessment Report (AR5)",
        "description": (
            "For gas-specific factors when a matching AR5 GWP "
            "dataset is available."
        )
    },
    {
        "id": "ipcc_ar6",
        "name": "IPCC Sixth Assessment Report (AR6)",
        "description": (
            "For gas-specific factors when a matching AR6 GWP "
            "dataset is available."
        )
    }
]

ACCOUNTING_FRAMEWORKS = [
    {
        "id": "ghg_protocol_corporate",
        "name": "GHG Protocol Corporate Standard",
        "type": "organisational_accounting"
    },
    {
        "id": "iso_14064_1",
        "name": "ISO 14064-1",
        "type": "organisational_quantification_and_reporting"
    },
    {
        "id": "pcaf",
        "name": "PCAF Financed Emissions",
        "type": "financed_emissions"
    }
]


# ============================================================
# 5. DATA FILE SCHEMAS
# ============================================================

# backend/data/activity_factors.csv must have these columns:
#
# factor_id
# source_id
# dataset_year
# geography
# industry_id
# process_id
# activity_id
# activity_unit
# factor_value
# output_unit
# gas
# gwp_basis
# scope
# source_name
# source_release
# source_url
# source_location
#
# Allowed output_unit values:
#
# kgCO2e = factor produces kg CO2 equivalent per activity unit
# tCO2e  = factor produces tonnes CO2 equivalent per activity unit
# kg_gas = factor produces kg of the specified gas per activity unit
#
# For kg_gas rows, gas must identify the gas and gwp_basis must
# be "gas_mass". The engine will look up the selected GWP value.
#
# For kgCO2e / tCO2e rows, gwp_basis must match the basis on
# which the source factor was published, e.g. source_defined.
#
# backend/data/gwp_values.csv must have these columns:
#
# gwp_basis
# gas
# gwp_value
# source_name
# source_release
# source_url
# source_location


class DatasetConfigurationError(Exception):
    """Raised when imported source data is malformed."""


FACTOR_REQUIRED_COLUMNS = [
    "factor_id",
    "source_id",
    "dataset_year",
    "geography",
    "industry_id",
    "process_id",
    "activity_id",
    "activity_unit",
    "factor_value",
    "output_unit",
    "gas",
    "gwp_basis",
    "scope",
    "source_name",
    "source_release",
    "source_url",
    "source_location"
]

GWP_REQUIRED_COLUMNS = [
    "gwp_basis",
    "gas",
    "gwp_value",
    "source_name",
    "source_release",
    "source_url",
    "source_location"
]

FACTOR_CACHE = {
    "signature": None,
    "rows": []
}

GWP_CACHE = {
    "signature": None,
    "rows": []
}


# ============================================================
# 6. DATASET LOADING
# ============================================================

def file_signature(path):
    """Return a file signature used to refresh the cache on change."""

    try:
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def read_csv_file(path, required_columns):
    """Read a CSV file and validate its column names."""

    if not os.path.isfile(path):
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            headers = [
                (header or "").strip()
                for header in (reader.fieldnames or [])
            ]

            if not headers:
                raise DatasetConfigurationError(
                    f"{os.path.basename(path)} has no CSV header."
                )

            missing_columns = sorted(
                set(required_columns) - set(headers)
            )

            if missing_columns:
                raise DatasetConfigurationError(
                    f"{os.path.basename(path)} is missing required "
                    f"columns: {', '.join(missing_columns)}."
                )

            reader.fieldnames = headers

            rows = []

            for row in reader:
                cleaned = {
                    str(key).strip(): (
                        value.strip()
                        if isinstance(value, str)
                        else ""
                    )
                    for key, value in row.items()
                    if key is not None
                }

                if not any(cleaned.values()):
                    continue

                rows.append(cleaned)

            return rows

    except (OSError, csv.Error) as error:
        raise DatasetConfigurationError(
            f"Unable to read {os.path.basename(path)}: {error}"
        ) from error


def load_factor_rows():
    """Load and cache normalised emission-factor records."""

    signature = file_signature(ACTIVITY_FACTORS_FILE)

    if signature is None:
        FACTOR_CACHE["signature"] = None
        FACTOR_CACHE["rows"] = []
        return []

    if FACTOR_CACHE["signature"] == signature:
        return FACTOR_CACHE["rows"]

    raw_rows = read_csv_file(
        ACTIVITY_FACTORS_FILE,
        FACTOR_REQUIRED_COLUMNS
    )

    allowed_output_units = {
        "kgco2e": "kgCO2e",
        "tco2e": "tCO2e",
        "kg_gas": "kg_gas"
    }

    normalised_rows = []

    for row_number, row in enumerate(raw_rows, start=2):
        try:
            factor_value = float(row["factor_value"])
            scope = int(row["scope"])
            year = row["dataset_year"].strip()

            if not math.isfinite(factor_value):
                raise ValueError("factor_value must be finite")

            if not year.isdigit() or len(year) != 4:
                raise ValueError("dataset_year must be a four-digit year")

            if scope not in (1, 2, 3):
                raise ValueError("scope must be 1, 2 or 3")

            output_unit_key = row["output_unit"].strip().lower()

            if output_unit_key not in allowed_output_units:
                raise ValueError(
                    "output_unit must be kgCO2e, tCO2e or kg_gas"
                )

            output_unit = allowed_output_units[output_unit_key]

            gas = row["gas"].strip().upper()
            gwp_basis = row["gwp_basis"].strip().lower()

            if output_unit == "kg_gas" and not gas:
                raise ValueError(
                    "gas is required for kg_gas factor rows"
                )

            if output_unit == "kg_gas" and gwp_basis != "gas_mass":
                raise ValueError(
                    "kg_gas rows must use gwp_basis=gas_mass"
                )

            if output_unit in {"kgCO2e", "tCO2e"} and not gwp_basis:
                raise ValueError(
                    "CO2e factor rows require a gwp_basis"
                )

            normalised_rows.append({
                **row,
                "factor_value": factor_value,
                "scope": scope,
                "dataset_year": year,
                "output_unit": output_unit,
                "gas": gas,
                "gwp_basis": gwp_basis
            })

        except (ValueError, TypeError) as error:
            raise DatasetConfigurationError(
                f"{os.path.basename(ACTIVITY_FACTORS_FILE)}, "
                f"row {row_number}: {error}."
            ) from error

    FACTOR_CACHE["signature"] = signature
    FACTOR_CACHE["rows"] = normalised_rows

    logger.info(
        "Loaded %s emission-factor records.",
        len(normalised_rows)
    )

    return normalised_rows


def load_gwp_rows():
    """Load and cache normalised GWP records."""

    signature = file_signature(GWP_VALUES_FILE)

    if signature is None:
        GWP_CACHE["signature"] = None
        GWP_CACHE["rows"] = []
        return []

    if GWP_CACHE["signature"] == signature:
        return GWP_CACHE["rows"]

    raw_rows = read_csv_file(
        GWP_VALUES_FILE,
        GWP_REQUIRED_COLUMNS
    )

    normalised_rows = []

    for row_number, row in enumerate(raw_rows, start=2):
        try:
            gwp_value = float(row["gwp_value"])

            if not math.isfinite(gwp_value) or gwp_value <= 0:
                raise ValueError(
                    "gwp_value must be a finite positive number"
                )

            normalised_rows.append({
                **row,
                "gwp_basis": row["gwp_basis"].strip().lower(),
                "gas": row["gas"].strip().upper(),
                "gwp_value": gwp_value
            })

        except (ValueError, TypeError) as error:
            raise DatasetConfigurationError(
                f"{os.path.basename(GWP_VALUES_FILE)}, "
                f"row {row_number}: {error}."
            ) from error

    GWP_CACHE["signature"] = signature
    GWP_CACHE["rows"] = normalised_rows

    logger.info(
        "Loaded %s GWP records.",
        len(normalised_rows)
    )

    return normalised_rows


@app.errorhandler(DatasetConfigurationError)
def handle_dataset_configuration_error(error):
    logger.error("Dataset configuration error: %s", error)

    return jsonify({
        "success": False,
        "error": str(error)
    }), 500


# ============================================================
# 7. GENERAL HELPERS
# ============================================================

def valid_report_id(report_id):
    return (
        isinstance(report_id, str)
        and bool(report_id.strip())
        and len(report_id) <= 200
        and "/" not in report_id
        and report_id not in {".", ".."}
    )


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def to_finite_number(value):
    try:
        number = float(value)

        if math.isfinite(number):
            return number
    except (ValueError, TypeError):
        pass

    return 0.0


def parse_year(value, field_name):
    year_text = str(value or "").strip()

    if not year_text.isdigit() or len(year_text) != 4:
        raise ValueError(
            f"{field_name} must be a four-digit year."
        )

    return year_text


def find_industry(industry_id):
    for industry in INDUSTRY_CATALOG:
        if industry["id"] == industry_id:
            return industry

    return None


LABEL_MAX_LENGTH = 200


def clean_label(value, field_name, max_length=LABEL_MAX_LENGTH):
    """
    Normalise an optional free-text metadata label (industry, process or
    activity name). Labels are report metadata only; they never select a
    factor and are not checked against the Python catalogue.
    """

    if value is None:
        return ""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text.")

    text = " ".join(value.split())

    if len(text) > max_length:
        raise ValueError(
            f"{field_name} cannot exceed {max_length} characters."
        )

    return text


def parse_scope_filter(value, field_name="scope"):
    """Parse 1, '1' or 'Scope 1' to an int, or return None if blank."""

    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be 1, 2 or 3.")

    text = str(value).strip().lower().replace("scope", "").strip()

    if not text:
        return None

    if text not in {"1", "2", "3"}:
        raise ValueError(f"{field_name} must be 1, 2 or 3.")

    return int(text)



def factor_dataset_registry():
    """Return successfully imported dataset releases from Firestore."""

    results = []

    for snapshot in db.collection("factor_datasets").stream():
        metadata = snapshot.to_dict() or {}

        # Only fully imported datasets are available for selection.
        if metadata.get("import_status") != "imported":
            continue

        source_id = str(metadata.get("source_id") or "").strip()

        try:
            dataset_year = int(metadata.get("dataset_year"))
        except (TypeError, ValueError):
            logger.warning(
                "Skipping dataset %s: invalid dataset year.",
                snapshot.id
            )
            continue

        if not source_id:
            logger.warning(
                "Skipping dataset %s: missing source ID.",
                snapshot.id
            )
            continue

        geography = str(metadata.get("geography") or "").strip()

        results.append({
            "dataset_id": snapshot.id,
            "source_id": source_id,
            "source_name": metadata.get("source_name"),
            "source_url": metadata.get("source_url"),
            "source_release": metadata.get("source_release"),
            "dataset_year": dataset_year,
            "import_status": metadata.get("import_status"),

            "geographies": [geography] if geography else [],

            # These require separately reviewed activity mappings.
            # Do not infer industry coverage from raw source factors.
            "industries": [],

            "factor_count": metadata.get(
                "record_count_imported", 0
            ),
            "record_count_expected": metadata.get(
                "record_count_expected", 0
            ),
            "record_count_imported": metadata.get(
                "record_count_imported", 0
            ),

            "schema_version": metadata.get("schema_version"),
            "source_updated_at": metadata.get("source_updated_at"),
            "source_file_name": metadata.get("source_file_name"),
            "source_file_sha256": metadata.get("source_file_sha256"),
            "normalized_file_name": metadata.get("normalized_file_name"),
            "normalized_file_sha256": metadata.get(
                "normalized_file_sha256"
            )
        })

    return sorted(
        results,
        key=lambda item: (
            item["source_id"],
            item["dataset_year"],
            str(item["source_release"] or "")
        )
    )



def dataset_available_for_profile(
    source_id,
    dataset_year,
    geography,
    industry_id
):
    for row in load_factor_rows():
        if (
            row["source_id"] == source_id
            and row["dataset_year"] == dataset_year
            and row["geography"].casefold() == geography.casefold()
            and row["industry_id"] == industry_id
        ):
            return True

    return False



def availability_summary(dataset_available):
    """
    Describe the three different things "available" can mean, so a
    client does not read an imported dataset as "every activity can be
    calculated".

    1. dataset_available: an imported factor dataset exists.
    2. factor candidates: listed per report from its pinned dataset by
       GET /api/factors. A candidate is not assumed applicable.
    3. calculation: succeeds only for one explicitly selected factor_id
       that passes validation. No industry/process mapping is needed.
    """

    return {
        "dataset_available": bool(dataset_available),
        "factor_candidates": {
            "endpoint": "/api/factors",
            "requires": ["report_id"],
            "scope": "report_pinned_dataset",
            "applicability_assumed": False
        },
        "calculation": {
            "mode": "explicit_factor_selection",
            "endpoint": "/api/calculate-and-log",
            "requires": [
                "report_id", "factor_id", "selected_unit", "raw_value"
            ],
            "industry_process_mapping_required": False,
            "availability_by_activity": "not_determined_by_dataset_import"
        }
    }


def enriched_industry_catalog():
    """
    Template metadata for the UI. Industries, processes and activities
    here are labels and suggested units only.

    supported_units / supported_factors / curated_suggestions_available
    list OPTIONAL curated suggestions, derived only from approved
    mappings whose dataset and factor are still valid in Firestore. They
    are not a precondition for calculation, and their absence does not
    mean an activity cannot be calculated with an explicitly selected
    factor.
    """

    industries = deepcopy(INDUSTRY_CATALOG)
    activity_lookup = {}
    units_by_activity = {}
    factors_by_activity = {}

    for industry in industries:
        for process in industry["processes"]:
            for activity in process["activities"]:
                key = (
                    industry["id"],
                    process["id"],
                    activity["id"]
                )

                activity_lookup[key] = activity
                units_by_activity[key] = set()
                factors_by_activity[key] = {}

                activity["supported_units"] = []
                activity["supported_factors"] = []
                activity["factor_data_available"] = False

    # Only approved mappings can establish activity coverage.
    approved_mappings = (
        db.collection("activity_factor_mappings")
        .where(filter=FieldFilter("status", "==", "approved"))
        .stream()
    )

    dataset_cache = {}
    factor_cache = {}

    for mapping_snapshot in approved_mappings:
        mapping = mapping_snapshot.to_dict() or {}

        industry_id = mapping.get("industry_id")
        process_id = mapping.get("process_id")
        activity_id = mapping.get("activity_id")

        activity_key = (
            industry_id,
            process_id,
            activity_id
        )

        # Ignore mappings that don't match an application activity.
        if activity_key not in activity_lookup:
            continue

        dataset_id = str(mapping.get("dataset_id") or "").strip()
        factor_id = str(mapping.get("factor_id") or "").strip()

        if not dataset_id or not factor_id:
            continue

        # Load each dataset's metadata at most once per request.
        if dataset_id not in dataset_cache:
            dataset_snapshot = (
                db.collection("factor_datasets")
                .document(dataset_id)
                .get()
            )

            dataset_cache[dataset_id] = (
                dataset_snapshot.to_dict()
                if dataset_snapshot.exists
                else None
            )

        dataset = dataset_cache[dataset_id]

        if not dataset or dataset.get("import_status") != "imported":
            continue

        dataset_year = dataset.get("dataset_year")
        source_id = dataset.get("source_id")
        source_release = dataset.get("source_release")

        if (
            str(mapping.get("dataset_year")) != str(dataset_year)
            or mapping.get("source_id") != source_id
            or str(mapping.get("source_release")) != str(source_release)
        ):
            continue

        # Cache each factor lookup for this request.
        factor_key = (dataset_id, factor_id)

        if factor_key not in factor_cache:
            factor_snapshot = (
                db.collection("factor_datasets")
                .document(dataset_id)
                .collection("factors")
                .document(factor_id)
                .get()
            )

            factor_cache[factor_key] = (
                factor_snapshot.to_dict()
                if factor_snapshot.exists
                else None
            )

        factor = factor_cache[factor_key]

        if not factor or factor.get("factor_status") != "present":
            continue

        factor_value = factor.get("factor_value")

        if (
            isinstance(factor_value, bool)
            or not isinstance(factor_value, (int, float))
            or not math.isfinite(factor_value)
            or factor_value <= 0
        ):
            continue

        # Only complete aggregate CO2e factors are supported here.
        if str(factor.get("ghg_unit", "")).strip().casefold() != "kg co2e":
            continue

        activity_unit = factor.get("activity_unit")
        scope_number = factor.get("scope_number")

        if (
            not activity_unit
            or mapping.get("activity_unit") != activity_unit
            or scope_number not in (1, 2, 3)
            or mapping.get("scope_number") != scope_number
        ):
            continue

        # Verify factor provenance against the registered dataset.
        if (
            factor.get("dataset_id") != dataset_id
            or factor.get("source_id") != source_id
            or str(factor.get("dataset_year")) != str(dataset_year)
            or str(factor.get("source_release")) != str(source_release)
        ):
            continue

        units_by_activity[activity_key].add(activity_unit)
        factors_by_activity[activity_key][factor_id] = {
            "factor_id": factor_id,
            "dataset_id": dataset_id,
            "source_id": source_id,
            "source_name": factor.get("source_name") or dataset.get("source_name"),
            "dataset_year": dataset_year,
            "source_release": source_release,
            "geography": dataset.get("geography"),
            "activity_unit": activity_unit,
            "factor_value": factor_value,
            "factor_output_unit": "kg CO2e",
            "scope_number": scope_number,
            "factor_label": " · ".join(
                str(factor.get(field) or "").strip()
                for field in (
                    "category_level_1",
                    "category_level_2",
                    "category_level_3",
                    "column_text"
                )
                if str(factor.get(field) or "").strip()
            ) or factor_id,
            "source_url": factor.get("source_url") or dataset.get("source_url")
        }

    # Only validated, approved mappings contribute to availability.
    for activity_key, activity in activity_lookup.items():
        supported_units = sorted(units_by_activity[activity_key])
        supported_factors = sorted(
            factors_by_activity[activity_key].values(),
            key=lambda item: (
                item.get("source_id") or "",
                int(item.get("dataset_year") or 0),
                item.get("source_release") or "",
                item.get("activity_unit") or "",
                item.get("factor_id") or ""
            )
        )

        activity["supported_units"] = supported_units
        activity["supported_factors"] = supported_factors

        # Curated suggestions only. Kept under the legacy key too so
        # existing clients keep working; the legacy name does not mean
        # "calculation is available".
        activity["curated_suggestions_available"] = bool(supported_factors)
        activity["factor_data_available"] = bool(supported_factors)

        # Calculation never depends on this activity's suggestions.
        activity["factor_selection_required"] = True
        activity["calculation_mode"] = "explicit_factor_selection"

    return industries



def available_gwp_bases():
    """
    Return GWP bases supported by the currently imported factor data.

    The current calculation path supports complete aggregate CO2e
    factors using the source-published basis. Separate IPCC AR5/AR6
    GWP datasets are not yet registered in Firestore.
    """

    available = set()

    for dataset in factor_dataset_registry():
        dataset_id = dataset["dataset_id"]

        factors_ref = (
            db.collection("factor_datasets")
            .document(dataset_id)
            .collection("factors")
        )

        candidates = (
            factors_ref
            .where(
                filter=FieldFilter(
                    "factor_status", "==", "present"
                )
            )
            .where(
                filter=FieldFilter(
                    "ghg_unit", "==", "kg CO2e"
                )
            )
            .stream()
        )

        for candidate in candidates:
            factor = candidate.to_dict() or {}
            factor_value = factor.get("factor_value")

            if (
                isinstance(factor_value, bool)
                or not isinstance(factor_value, (int, float))
                or not math.isfinite(factor_value)
                or factor_value <= 0
            ):
                continue

            available.add("source_defined")
            break

    return sorted(available)


def build_dataset_status():
    """Report Firestore datasets separately from legacy local CSV files."""

    registry = factor_dataset_registry()

    # Retain legacy CSV diagnostics without using them to determine
    # whether an imported Firestore dataset exists.
    local_factor_rows = load_factor_rows()
    local_gwp_rows = load_gwp_rows()

    missing_files = []

    if not os.path.isfile(ACTIVITY_FACTORS_FILE):
        missing_files.append("activity_factors.csv")

    if not os.path.isfile(GWP_VALUES_FILE):
        missing_files.append("gwp_values.csv")

    imported_factor_records = sum(
        int(item.get("record_count_imported") or 0)
        for item in registry
    )

    factor_data_available = bool(registry)

    return {
        # Authoritative dataset registry
        "registry_source": "firestore",
        "registered_dataset_count": len(registry),
        "available_factor_datasets": registry,
        "factor_data_available": factor_data_available,
        "imported_factor_records": imported_factor_records,

        # Legacy local-file diagnostics
        "activity_factor_file": "data/activity_factors.csv",
        "activity_factor_file_loaded": os.path.isfile(
            ACTIVITY_FACTORS_FILE
        ),
        "activity_factor_records": len(local_factor_rows),

        "gwp_file": "data/gwp_values.csv",
        "gwp_file_loaded": os.path.isfile(GWP_VALUES_FILE),
        "gwp_records": len(local_gwp_rows),

        "missing_files": missing_files,
        "legacy_local_files_missing": missing_files,

        # GWP availability still uses the existing local-file logic.
        "available_gwp_bases": available_gwp_bases(),

        # Dataset import does not prove the full calculation workflow
        # is ready. Approval and end-to-end tests remain outstanding.
        # Importing a dataset does not make every activity calculable.
        # Readiness is decided per report (pinned dataset) and per
        # explicitly selected factor, so no global "ready" is claimed.
        "dataset_available": factor_data_available,
        "calculation_ready": False,
        "calculation_readiness_status": (
            "determined_per_report_and_selected_factor"
            if factor_data_available
            else "no_imported_factor_dataset"
        ),
        "availability": availability_summary(factor_data_available),

        "message": (
            "Imported factor datasets are available from Firestore. "
            "Legacy local CSV status is reported separately. "
            "The calculation workflow is not yet verified end to end."
            if factor_data_available
            else (
                "No successfully imported factor datasets were found "
                "in Firestore. No fallback emission factors are used."
            )
        )
    }

# ============================================================
# 8. HEALTH / CONFIGURATION APIs
# ============================================================

@app.get("/api/health")
def health_check():
    return jsonify({
        "success": True,
        "service": "carbon-footprinting-api",
        "calculation_version": CALCULATION_VERSION,
        "emissions_unit": EMISSIONS_UNIT
    })


@app.get("/api/catalog")
@app.get("/api/config")
def get_application_catalog():
    return jsonify({
        "success": True,

        "industries": enriched_industry_catalog(),

        "factor_sources": FACTOR_SOURCES,
        "gwp_basis_options": GWP_BASIS_OPTIONS,
        "accounting_frameworks": ACCOUNTING_FRAMEWORKS,

        "reporting_years": sorted({
            int(item["dataset_year"])
            for item in factor_dataset_registry()
        }, reverse=True),

        "datasets": build_dataset_status()
    })


@app.get("/api/industries")
def get_industries():
    return jsonify({
        "success": True,
        "industries": enriched_industry_catalog(),
        "availability": availability_summary(
            bool(factor_dataset_registry())
        )
    })


@app.get("/api/industries/<industry_id>")
def get_industry(industry_id):
    for industry in enriched_industry_catalog():
        if industry["id"] == industry_id:
            return jsonify({
                "success": True,
                "industry": industry
            })

    return jsonify({
        "success": False,
        "error": "Industry not found."
    }), 404


@app.get("/api/standards")
def get_standards():
    registry = factor_dataset_registry()

    source_options = []

    for source in FACTOR_SOURCES:
        dataset_rows = [
            item for item in registry
            if item["source_id"] == source["id"]
        ]

        source_options.append({
            **source,
            "available_dataset_years": sorted({
                int(item["dataset_year"])
                for item in dataset_rows
            }, reverse=True),
            "dataset_available": bool(dataset_rows)
        })

    gwp_available = set(available_gwp_bases())

    return jsonify({
        "success": True,

        "factor_sources": source_options,

        "gwp_basis_options": [
            {
                **option,
                "available": option["id"] in gwp_available
            }
            for option in GWP_BASIS_OPTIONS
        ],

        "accounting_frameworks": ACCOUNTING_FRAMEWORKS
    })


@app.get("/api/datasets")
def get_datasets():
    return jsonify({
        "success": True,
        "datasets": build_dataset_status()
    })

@app.get("/api/factor-datasets/<dataset_id>/factors")

def get_imported_factor_records(dataset_id):
    """
    Browse imported source factors from Firestore.

    Supports pagination and optional exact filters.
    This endpoint reads source records; it does not calculate emissions.
    """

    try:
        dataset_ref = (
            db.collection("factor_datasets")
            .document(dataset_id)
        )

        dataset_snapshot = dataset_ref.get()

        if not dataset_snapshot.exists:
            return jsonify({
                "success": False,
                "error": "Factor dataset not found."
            }), 404

        dataset_metadata = dataset_snapshot.to_dict() or {}

        if dataset_metadata.get("import_status") != "imported":
            return jsonify({
                "success": False,
                "error": "The factor dataset has not completed importing."
            }), 409

        factors_ref = dataset_ref.collection("factors")
        query = factors_ref

        # Optional exact filters.
        scope_value = request.args.get("scope", "").strip()

        if scope_value:
            normalized_scope = (
                scope_value.lower()
                .replace("scope", "")
                .strip()
            )

            if normalized_scope not in {"1", "2", "3"}:
                return jsonify({
                    "success": False,
                    "error": "scope must be 1, 2 or 3."
                }), 400

            query = query.where(
                "scope_number",
                "==",
                int(normalized_scope)
            )

        filters = {
            "activity_unit": request.args.get("unit", "").strip(),
            "ghg_unit": request.args.get("ghg_unit", "").strip(),
            "category_level_1": request.args.get(
                "category_level_1", ""
            ).strip(),
            "category_level_2": request.args.get(
                "category_level_2", ""
            ).strip(),
            "category_level_3": request.args.get(
                "category_level_3", ""
            ).strip(),
            "factor_status": request.args.get("status", "").strip(),
        }

        allowed_statuses = {
            "present",
            "missing",
            "zero_requires_review",
            "non_numeric",
        }

        if (
            filters["factor_status"]
            and filters["factor_status"] not in allowed_statuses
        ):
            return jsonify({
                "success": False,
                "error": (
                    "Unsupported status. Choose present, missing, "
                    "zero_requires_review or non_numeric."
                )
            }), 400

        for field, value in filters.items():
            if value:
                query = query.where(field, "==", value)

        # Limit page size so a request cannot download the entire dataset.
        try:
            page_size = int(request.args.get("limit", "50"))
        except ValueError:
            return jsonify({
                "success": False,
                "error": "limit must be an integer."
            }), 400

        if page_size < 1 or page_size > 100:
            return jsonify({
                "success": False,
                "error": "limit must be between 1 and 100."
            }), 400

        # Continue after the last document from the previous page.
        after_id = request.args.get("after", "").strip()

        if after_id:
            cursor_snapshot = factors_ref.document(after_id).get()

            if not cursor_snapshot.exists:
                return jsonify({
                    "success": False,
                    "error": "The pagination cursor was not found."
                }), 400

            query = query.start_after(cursor_snapshot)

        snapshots = list(query.limit(page_size + 1).stream())

        has_more = len(snapshots) > page_size
        page_snapshots = snapshots[:page_size]

        records = []

        for snapshot in page_snapshots:
            record = snapshot.to_dict() or {}

            records.append({
                "factor_id": record.get("factor_id", snapshot.id),
                "dataset_year": record.get("dataset_year"),
                "source_name": record.get("source_name"),
                "source_release": record.get("source_release"),
                "source_url": record.get("source_url"),

                "scope_label": record.get("scope_label"),
                "scope_number": record.get("scope_number"),

                "category_level_1": record.get("category_level_1"),
                "category_level_2": record.get("category_level_2"),
                "category_level_3": record.get("category_level_3"),
                "category_level_4": record.get("category_level_4"),
                "column_text": record.get("column_text"),

                "activity_unit": record.get("activity_unit"),
                "ghg_unit": record.get("ghg_unit"),
                "factor_value": record.get("factor_value"),
                "factor_status": record.get("factor_status"),
            })

        return jsonify({
            "success": True,
            "dataset_id": dataset_id,
            "dataset_year": dataset_metadata.get("dataset_year"),
            "count": len(records),
            "limit": page_size,
            "has_more": has_more,
            "next_after": (
                page_snapshots[-1].id
                if has_more and page_snapshots
                else None
            ),
            "filters": {
                "scope": scope_value or None,
                **{
                    field: value or None
                    for field, value in filters.items()
                },
            },
            "factors": records,
        }), 200

    except Exception:
        logger.exception("Failed to browse imported factor records")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve factor records."
        }), 500

@app.get("/api/factors")
def get_available_factors():
    """
    Search aggregate CO2e factors in the imported Firestore dataset.

    This returns source-factor candidates. It does not claim that
    a candidate has already been verified for a business process.
    """

    try:
        report_id = request.args.get("report_id", "").strip()
        search_text = request.args.get("q", "").strip().casefold()
        selected_unit = request.args.get("unit", "").strip()
        scope_value = request.args.get("scope", "").strip()
        limit_text = request.args.get("limit", "50").strip()

        if not valid_report_id(report_id):
            return jsonify({
                "success": False,
                "error": "A valid report_id is required."
            }), 400

        try:
            page_size = int(limit_text)
        except ValueError:
            return jsonify({
                "success": False,
                "error": "limit must be an integer."
            }), 400

        if not 1 <= page_size <= 100:
            return jsonify({
                "success": False,
                "error": "limit must be between 1 and 100."
            }), 400

        if scope_value:
            scope_value = (
                scope_value.lower()
                .replace("scope", "")
                .strip()
            )

            if scope_value not in {"1", "2", "3"}:
                return jsonify({
                    "success": False,
                    "error": "scope must be 1, 2 or 3."
                }), 400

        # Load the report's selected methodology and factor year.
        report_ref = db.collection("reports").document(report_id)
        report_snapshot = report_ref.get()

        if not report_snapshot.exists:
            return jsonify({
                "success": False,
                "error": "Report not found. Create a configured report first."
            }), 404

        report = report_snapshot.to_dict() or {}
        config = report.get("configuration") or {}

        source_id = config.get("factor_source_id")
        dataset_year = config.get("factor_dataset_year")
        geography = str(config.get("geography", "")).strip()

        # The imported source currently contains UK DEFRA data.
        if source_id == "defra_desnz" and geography.casefold() != "uk":
            return jsonify({
                "success": False,
                "error": (
                    "This imported DEFRA dataset is for UK reporting. "
                    "No factor choices are offered for another geography."
                )
            }), 422

        # Candidates come only from the dataset release pinned to the
        # report, never from a source/year search.
        pinned_dataset_id = str(
            config.get("factor_dataset_id") or ""
        ).strip()

        if not pinned_dataset_id:
            return jsonify({
                "success": False,
                "error": (
                    "This report has no pinned factor dataset release, "
                    "so no factor candidates can be offered."
                ),
                "error_code": "NO_PINNED_DATASET"
            }), 409

        dataset_snapshot = (
            db.collection("factor_datasets")
            .document(pinned_dataset_id)
            .get()
        )

        if not dataset_snapshot.exists:
            return jsonify({
                "success": False,
                "error": "The report's pinned factor dataset was not found."
            }), 404

        dataset_metadata = dataset_snapshot.to_dict() or {}

        if (
            dataset_metadata.get("import_status") != "imported"
            or dataset_metadata.get("source_id") != source_id
            or str(dataset_metadata.get("dataset_year"))
            != str(dataset_year)
            or str(dataset_metadata.get("source_release"))
            != str(config.get("factor_dataset_release"))
            or str(dataset_metadata.get("geography") or "").casefold()
            != geography.casefold()
        ):
            return jsonify({
                "success": False,
                "error": (
                    "The pinned dataset does not match the report's "
                    "source, year, release or geography."
                ),
                "error_code": "PINNED_DATASET_MISMATCH"
            }), 409

        # Only return complete, aggregate CO2e records in this initial
        # calculation path. Do not mix total factors with gas components.
        factor_query = (
            dataset_snapshot.reference
            .collection("factors")
            .where("factor_status", "==", "present")
            .where("ghg_unit", "==", "kg CO2e")
        )

        # Equality filters are pushed to Firestore so a request does not
        # read every aggregate factor in the dataset.
        if selected_unit:
            factor_query = factor_query.where(
                "activity_unit", "==", selected_unit
            )

        if scope_value:
            factor_query = factor_query.where(
                "scope_number", "==", int(scope_value)
            )

        factors = []

        for factor_snapshot in factor_query.stream():
            factor = factor_snapshot.to_dict() or {}

            if selected_unit and factor.get("activity_unit") != selected_unit:
                continue

            if (
                scope_value
                and str(factor.get("scope_number")) != scope_value
            ):
                continue

            category_text = " ".join([
                str(factor.get("category_level_1") or ""),
                str(factor.get("category_level_2") or ""),
                str(factor.get("category_level_3") or ""),
                str(factor.get("category_level_4") or ""),
                str(factor.get("column_text") or ""),
            ]).casefold()

            if search_text and search_text not in category_text:
                continue

            value = factor.get("factor_value")

            # The import marks zero factors for review. This extra check
            # prevents them from becoming usable factors in this endpoint.
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                continue

            factors.append({
                "factor_id": factor.get("factor_id", factor_snapshot.id),
                "source_id": factor.get("source_id"),
                "source_name": factor.get("source_name"),
                "source_release": factor.get("source_release"),
                "source_url": factor.get("source_url"),
                "dataset_id": dataset_snapshot.id,
                "dataset_year": factor.get("dataset_year"),
                "dataset_release": dataset_metadata.get("source_release"),
                "geography": dataset_metadata.get("geography"),

                "scope_label": factor.get("scope_label"),
                "scope_number": factor.get("scope_number"),

                "category_level_1": factor.get("category_level_1"),
                "category_level_2": factor.get("category_level_2"),
                "category_level_3": factor.get("category_level_3"),
                "category_level_4": factor.get("category_level_4"),
                "column_text": factor.get("column_text"),

                "activity_unit": factor.get("activity_unit"),
                "ghg_unit": factor.get("ghg_unit"),
                "factor_value": value,
                "factor_status": factor.get("factor_status"),
            })

        factors.sort(
            key=lambda item: (
                item.get("category_level_1") or "",
                item.get("category_level_2") or "",
                item.get("category_level_3") or "",
                item.get("activity_unit") or "",
                item["factor_id"],
            )
        )

        total_matches = len(factors)
        factors = factors[:page_size]

        return jsonify({
            "success": True,
            "report_id": report_id,
            "dataset_id": dataset_snapshot.id,
            "dataset_year": dataset_metadata.get("dataset_year"),
            "dataset_release": dataset_metadata.get("source_release"),
            "geography": dataset_metadata.get("geography"),
            "count": len(factors),
            "total_matches": total_matches,
            "limit": page_size,
            "filters": {
                "q": search_text or None,
                "unit": selected_unit or None,
                "scope": scope_value or None,
            },
            "mapping_note": (
                "These are source-factor candidates from the report's "
                "pinned dataset. None is assumed applicable to your "
                "activity; choose one explicitly and send its factor_id "
                "(with dataset_id and dataset_release) to calculate."
            ),
            "factors": factors,
        }), 200

    except DatasetConfigurationError:
        raise

    except Exception:
        logger.exception("Failed to retrieve factors from Firestore")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve emission-factor candidates."
        }), 500

@app.post("/api/activity-factor-mappings")
def propose_activity_factor_mapping():
    """
    Save a proposed relationship between an imported source factor
    and an application activity.

    New mappings remain pending review; they are not automatically
    available for carbon calculations.
    """

    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "A valid JSON request body is required."
            }), 400

        dataset_id = str(data.get("dataset_id", "")).strip()
        factor_id = str(data.get("factor_id", "")).strip()
        industry_id = str(data.get("industry_id", "")).strip()
        process_id = str(data.get("process_id", "")).strip()
        activity_id = str(data.get("activity_id", "")).strip()
        mapping_note = str(data.get("mapping_note", "")).strip()

        required_values = {
            "dataset_id": dataset_id,
            "factor_id": factor_id,
            "industry_id": industry_id,
            "process_id": process_id,
            "activity_id": activity_id
        }

        missing = [
            name for name, value in required_values.items()
            if not value
        ]

        if missing:
            return jsonify({
                "success": False,
                "error": (
                    "Required fields are missing: "
                    + ", ".join(missing)
                )
            }), 400

        # Firestore document IDs cannot contain a slash.
        if any(
            "/" in value
            for value in required_values.values()
        ):
            return jsonify({
                "success": False,
                "error": "Identifiers cannot contain '/'."
            }), 400

        # Verify the source dataset exists and finished importing.
        dataset_ref = (
            db.collection("factor_datasets")
            .document(dataset_id)
        )

        dataset_snapshot = dataset_ref.get()

        if not dataset_snapshot.exists:
            return jsonify({
                "success": False,
                "error": "The source dataset was not found."
            }), 404

        dataset = dataset_snapshot.to_dict() or {}

        if dataset.get("import_status") != "imported":
            return jsonify({
                "success": False,
                "error": "The source dataset is not fully imported."
            }), 409

        # Retrieve the actual factor; do not accept a factor value
        # supplied by the caller.
        factor_snapshot = (
            dataset_ref.collection("factors")
            .document(factor_id)
            .get()
        )

        if not factor_snapshot.exists:
            return jsonify({
                "success": False,
                "error": (
                    "The selected factor does not exist "
                    "in the chosen dataset."
                )
            }), 404

        factor = factor_snapshot.to_dict() or {}

        if factor.get("factor_status") != "present":
            return jsonify({
                "success": False,
                "error": (
                    "Only source factors marked present can be "
                    "proposed. Missing or zero-review factors "
                    "cannot be mapped for calculation."
                )
            }), 422

        # This initial mapping workflow supports only complete,
        # aggregate kg CO2e factors.
        if str(factor.get("ghg_unit", "")).strip().casefold() != "kg co2e":
            return jsonify({
                "success": False,
                "error": (
                    "This mapping workflow currently accepts only "
                    "complete aggregate 'kg CO2e' factors. "
                    "Component factors need a separate validated method."
                )
            }), 422

        factor_value = factor.get("factor_value")

        if (
            isinstance(factor_value, bool)
            or not isinstance(factor_value, (int, float))
            or not math.isfinite(factor_value)
            or factor_value <= 0
        ):
            return jsonify({
                "success": False,
                "error": "The selected factor has no valid positive value."
            }), 422

        scope_number = factor.get("scope_number")

        if scope_number not in (1, 2, 3):
            return jsonify({
                "success": False,
                "error": "The source factor has no valid scope."
            }), 422

        # The mapping references an existing source factor. It does not
        # duplicate or hardcode the factor's numeric value.
        mapping_ref = db.collection(
            "activity_factor_mappings"
        ).document()

        mapping = {
            "mapping_id": mapping_ref.id,

            "dataset_id": dataset_id,
            "factor_id": factor_id,
            "source_id": dataset.get("source_id"),
            "dataset_year": dataset.get("dataset_year"),
            "source_release": dataset.get("source_release"),

            "industry_id": industry_id,
            "process_id": process_id,
            "activity_id": activity_id,

            "activity_unit": factor.get("activity_unit"),
            "scope_number": scope_number,

            "mapping_note": mapping_note,

            # A proposed mapping must be reviewed before use.
            "status": "pending_review",

            "created_at": utc_timestamp()
        }

        mapping_ref.set(mapping)

        return jsonify({
            "success": True,
            "mapping": mapping,
            "message": (
                "Mapping proposal saved. It requires review before "
                "it can be used for calculations."
            )
        }), 201

    except Exception:
        logger.exception("Failed to save activity-factor mapping")

        return jsonify({
            "success": False,
            "error": "Unable to save the mapping proposal."
        }), 500


def mapping_review_auth_error():
    """Require the configured reviewer token for review operations."""

    if not MAPPING_REVIEW_TOKEN or not MAPPING_REVIEWER_ID:
        return jsonify({
            "success": False,
            "error": (
                "Mapping review is not configured on this server."
            )
        }), 503

    supplied_token = request.headers.get(
        "X-Mapping-Review-Token", ""
    )

    if not supplied_token or not hmac.compare_digest(
        supplied_token, MAPPING_REVIEW_TOKEN
    ):
        return jsonify({
            "success": False,
            "error": "Reviewer authentication failed."
        }), 401

    return None


@app.get("/api/activity-factor-mappings")
def list_activity_factor_mappings():
    """List mapping proposals for the configured reviewer."""

    auth_error = mapping_review_auth_error()
    if auth_error is not None:
        return auth_error

    status_filter = request.args.get(
        "status", "pending_review"
    ).strip()

    allowed_statuses = {
        "pending_review", "approved", "rejected"
    }

    if status_filter not in allowed_statuses:
        return jsonify({
            "success": False,
            "error": (
                "status must be pending_review, approved or rejected."
            )
        }), 400

    try:
        limit = int(request.args.get("limit", "50"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "limit must be an integer."
        }), 400

    if not 1 <= limit <= 100:
        return jsonify({
            "success": False,
            "error": "limit must be between 1 and 100."
        }), 400

    try:
        query = (
            db.collection("activity_factor_mappings")
            .where(
                filter=FieldFilter(
                    "status", "==", status_filter
                )
            )
        )

        mappings = []

        for snapshot in query.stream():
            mapping = snapshot.to_dict() or {}
            mapping["mapping_id"] = snapshot.id
            mappings.append(mapping)

        # created_at is currently stored as an ISO UTC string.
        mappings.sort(
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True
        )

        total_matching = len(mappings)
        mappings = mappings[:limit]

        return jsonify({
            "success": True,
            "status": status_filter,
            "count": len(mappings),
            "total_matching": total_matching,
            "limit": limit,
            "mappings": mappings
        }), 200

    except Exception:
        logger.exception("Failed to list mapping proposals")
        return jsonify({
            "success": False,
            "error": "Unable to retrieve mapping proposals."
        }), 500


@app.post("/api/activity-factor-mappings/<mapping_id>/review")
def review_activity_factor_mapping(mapping_id):
    """Approve or reject one pending mapping with a reviewer decision."""

    auth_error = mapping_review_auth_error()
    if auth_error is not None:
        return auth_error

    if not mapping_id or "/" in mapping_id:
        return jsonify({
            "success": False,
            "error": "A valid mapping ID is required."
        }), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "A valid JSON request body is required."
        }), 400

    decision = str(data.get("decision", "")).strip().lower()
    review_note = str(data.get("review_note", "")).strip()

    if decision not in {"approved", "rejected"}:
        return jsonify({
            "success": False,
            "error": "decision must be approved or rejected."
        }), 400

    if not review_note or len(review_note) > 1000:
        return jsonify({
            "success": False,
            "error": (
                "Provide a review_note between 1 and 1000 characters."
            )
        }), 400

    mapping_ref = (
        db.collection("activity_factor_mappings")
        .document(mapping_id)
    )

    def approval_error(message, status_code):
        return {
            "http_status": status_code,
            "success": False,
            "error": message
        }

    @firestore.transactional
    def apply_review(transaction):
        mapping_snapshot = next(
            transaction.get(mapping_ref), None
            )

        if not mapping_snapshot.exists:
            return approval_error(
                "Mapping proposal not found.", 404
            )

        mapping = mapping_snapshot.to_dict() or {}

        if mapping.get("status") != "pending_review":
            return approval_error(
                "Only pending proposals can be reviewed.", 409
            )

        dataset_id = str(mapping.get("dataset_id") or "").strip()
        factor_id = str(mapping.get("factor_id") or "").strip()

        # Validate the factor and dataset before approval.
        # A rejected proposal can still be rejected if its source
        # has subsequently become unavailable.
        dataset = None
        factor = None

        if decision == "approved":
            if not dataset_id or not factor_id:
                return approval_error(
                    "The mapping is missing its dataset or factor ID.",
                    422
                )

            dataset_ref = (
                db.collection("factor_datasets")
                .document(dataset_id)
            )
            dataset_snapshot = next(
                transaction.get(dataset_ref), None
                )

            if not dataset_snapshot.exists:
                return approval_error(
                    "The mapped source dataset no longer exists.",
                    422
                )

            dataset = dataset_snapshot.to_dict() or {}

            if dataset.get("import_status") != "imported":
                return approval_error(
                    "The mapped dataset is not fully imported.",
                    422
                )

            factor_ref = (
                dataset_ref.collection("factors")
                .document(factor_id)
            )
            factor_snapshot = next(
                transaction.get(factor_ref), None)

            if not factor_snapshot.exists:
                return approval_error(
                    "The mapped source factor no longer exists.",
                    422
                )

            factor = factor_snapshot.to_dict() or {}

            if factor.get("factor_status") != "present":
                return approval_error(
                    "Only source factors marked present can be approved.",
                    422
                )

            value = factor.get("factor_value")

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                return approval_error(
                    "The mapped factor has no valid positive value.",
                    422
                )

            if (
                str(factor.get("ghg_unit") or "").strip().casefold()
                != "kg co2e"
            ):
                return approval_error(
                    "Only complete aggregate kg CO2e factors are supported.",
                    422
                )

            # Verify source identity, release, year, scope and unit.
            if (
                factor.get("dataset_id") != dataset_id
                or factor.get("source_id") != dataset.get("source_id")
                or str(factor.get("dataset_year"))
                != str(dataset.get("dataset_year"))
                or str(factor.get("source_release"))
                != str(dataset.get("source_release"))
                or mapping.get("source_id") != dataset.get("source_id")
                or str(mapping.get("dataset_year"))
                != str(dataset.get("dataset_year"))
                or str(mapping.get("source_release"))
                != str(dataset.get("source_release"))
                or mapping.get("activity_unit")
                != factor.get("activity_unit")
                or mapping.get("scope_number")
                != factor.get("scope_number")
                or factor.get("scope_number") not in (1, 2, 3)
            ):
                return approval_error(
                    "The mapping does not match the current source factor.",
                    422
                )

            # Validate that the application activity actually exists.
            industry = find_industry(
                str(mapping.get("industry_id") or "")
            )

            if not industry:
                return approval_error(
                    "The mapped industry is not in the application catalogue.",
                    422
                )

            process = next(
                (
                    item for item in industry.get("processes", [])
                    if item.get("id") == mapping.get("process_id")
                ),
                None
            )

            if not process:
                return approval_error(
                    "The mapped process is not in the selected industry.",
                    422
                )

            activity = next(
                (
                    item for item in process.get("activities", [])
                    if item.get("id") == mapping.get("activity_id")
                ),
                None
            )

            if not activity:
                return approval_error(
                    "The mapped activity is not in the selected process.",
                    422
                )

            if not dataset.get("geography"):
                return approval_error(
                    "The dataset must have explicit geography before approval.",
                    422
                )

        reviewed_at = utc_timestamp()

        updates = {
            "status": decision,
            "reviewed_at": reviewed_at,
            "reviewed_by": MAPPING_REVIEWER_ID,
            "review_note": review_note
        }

        if decision == "approved":
            updates["geography"] = dataset.get("geography")
            updates["approved_at"] = reviewed_at

        transaction.update(mapping_ref, updates)

        return {
            "http_status": 200,
            "success": True,
            "mapping": {
                **mapping,
                **updates,
                "mapping_id": mapping_id
            },
            "message": (
                "Mapping approved. Confirm that the reviewer has verified "
                "its scientific suitability for the specified activity."
                if decision == "approved"
                else "Mapping rejected and the decision recorded."
            )
        }

    try:
        result = apply_review(db.transaction())
        return jsonify(result), result["http_status"]

    except Exception:
        logger.exception("Failed to review mapping proposal")
        return jsonify({
            "success": False,
            "error": "Unable to review the mapping proposal."
        }), 500

# ============================================================
# 9. REPORT CREATION / CONFIGURATION
# ============================================================

@app.post("/api/reports")
def create_report():
    """
    Create a carbon audit report with an immutable calculation profile.

    Example request:
    {
      "report_name": "Steel Factory Annual Audit",
      "industry_id": "steel_manufacturing",
      "reporting_year": 2026,
      "factor_source_id": "defra_desnz",
      "factor_dataset_year": 2026,
      "geography": "UK",
      "gwp_basis": "source_defined",
      "accounting_framework": "ghg_protocol_corporate"
    }

    A report can be saved even if its dataset has not been imported.
    In that case, the response will indicate that calculation is not
    currently available. It will not invent or substitute factors.
    """

    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "A valid JSON request body is required."
            }), 400

        report_name = str(
            data.get("report_name", "")
        ).strip()

        industry_id = data.get("industry_id")
        source_id = data.get("factor_source_id")
        geography = str(
            data.get("geography", "")
        ).strip()

        gwp_basis = str(
            data.get("gwp_basis", "")
        ).strip().lower()

        framework_id = data.get("accounting_framework")

        if not report_name:
            return jsonify({
                "success": False,
                "error": "report_name is required."
            }), 400

        if len(report_name) > 200:
            return jsonify({
                "success": False,
                "error": "report_name cannot exceed 200 characters."
            }), 400

        # Industry is report metadata. Predefined catalogue IDs and
        # user-defined labels are both accepted; neither selects a factor.
        if (
            not isinstance(industry_id, str)
            or not industry_id.strip()
            or len(industry_id.strip()) > 100
        ):
            return jsonify({
                "success": False,
                "error": (
                    "industry_id is required (maximum 100 characters)."
                )
            }), 400

        industry_id = " ".join(industry_id.split())

        if not any(
            source["id"] == source_id
            for source in FACTOR_SOURCES
        ):
            return jsonify({
                "success": False,
                "error": "Select a valid factor source."
            }), 400

        if not geography:
            return jsonify({
                "success": False,
                "error": "geography is required."
            }), 400

        if gwp_basis not in {
            item["id"] for item in GWP_BASIS_OPTIONS
        }:
            return jsonify({
                "success": False,
                "error": "Select a valid GWP basis."
            }), 400

        if framework_id not in {
            item["id"] for item in ACCOUNTING_FRAMEWORKS
        }:
            return jsonify({
                "success": False,
                "error": "Select a valid accounting framework."
            }), 400

        reporting_year = parse_year(
            data.get("reporting_year"),
            "reporting_year"
        )

        factor_dataset_year = parse_year(
            data.get("factor_dataset_year"),
            "factor_dataset_year"
        )

        report_id = data.get("report_id")

        if report_id is None or not str(report_id).strip():
            report_id = f"CARBON-{uuid.uuid4().hex[:16].upper()}"
        else:
            report_id = str(report_id).strip()

        if not valid_report_id(report_id):
            return jsonify({
                "success": False,
                "error": "Invalid report_id."
            }), 400

        report_ref = (
            db.collection("reports")
            .document(report_id)
        )

        if report_ref.get().exists:
            return jsonify({
                "success": False,
                "error": (
                    "This report ID already exists. "
                    "Choose another ID rather than overwriting a report."
                ),
                "report_id": report_id
            }), 409

        
        # DEFRA's currently supported dataset is applicable to UK reporting.
        if source_id == "defra_desnz" and geography.casefold() != "uk":
            return jsonify({
                "success": False,
                "error": (
                    "The selected DEFRA dataset supports UK reporting only."
                )
            }), 422

        requested_dataset_id = str(
            data.get("factor_dataset_id") or ""
        ).strip()

        # Find imported releases matching the report's source, year and
        # geography. Never silently choose among multiple releases.
        matching_datasets = {}

        for snapshot in db.collection("factor_datasets").stream():
            metadata = snapshot.to_dict() or {}

            if (
                metadata.get("source_id") == source_id
                and str(metadata.get("dataset_year"))
                == str(factor_dataset_year)
                and metadata.get("import_status") == "imported"
                and str(metadata.get("geography") or "").casefold()
                == geography.casefold()
            ):
                matching_datasets[snapshot.id] = metadata

        if requested_dataset_id:
            if requested_dataset_id not in matching_datasets:
                return jsonify({
                    "success": False,
                    "error": (
                        "The selected dataset ID does not match an "
                        "imported dataset for this source, year and geography."
                    )
                }), 409

            selected_dataset_id = requested_dataset_id

        elif len(matching_datasets) == 1:
            # Convenient for the initial setup: pin the sole matching release.
            selected_dataset_id = next(iter(matching_datasets))

        elif len(matching_datasets) > 1:
            return jsonify({
                "success": False,
                "error": (
                    "Multiple dataset releases match this report. "
                    "Specify factor_dataset_id explicitly."
                ),
                "available_dataset_ids": sorted(matching_datasets.keys())
            }), 409

        else:
            # Preserve the existing ability to save a draft report
            # before its factor dataset has been imported.
            selected_dataset_id = None

        selected_metadata = (
            matching_datasets.get(selected_dataset_id)
            if selected_dataset_id
            else None
        )

        source_dataset_available = selected_metadata is not None

        configuration = {
            "industry_id": industry_id,
            "reporting_year": reporting_year,
            "factor_source_id": source_id,
            "factor_dataset_year": factor_dataset_year,
            "factor_dataset_id": selected_dataset_id,
            "factor_dataset_release": (
                selected_metadata.get("source_release")
                if selected_metadata
                else None
            ),
            "geography": geography,
            "gwp_basis": gwp_basis,
            "accounting_framework": framework_id
        }

        # A report is ready to calculate once its dataset release is
        # pinned. Each calculation then needs an explicitly selected,
        # individually validated factor_id; no per-process approved
        # mapping is required in this demo.
        calculation_ready = source_dataset_available

        now = utc_timestamp()

        # Display metadata is kept separate from the immutable calculation
        # configuration. The frontend may provide these optional fields.
        facility = data.get("facility") if isinstance(data.get("facility"), dict) else {}
        period = data.get("period") if isinstance(data.get("period"), dict) else {}
        facility_fields = (
            "name", "type", "address", "city", "state", "country",
            "pincode", "lat", "lng"
        )
        saved_facility = {
            key: facility.get(key, "")
            for key in facility_fields
        }
        saved_period = {
            key: period.get(key, "")
            for key in ("type", "start", "end")
        }
        industry_name = str(data.get("industry_name") or "").strip()
        subsector_id = str(data.get("subsector_id") or "").strip()
        subsector_name = str(data.get("subsector_name") or "").strip()

        report_payload = {
            "report_id": report_id,
            "report_name": report_name,
            "status": "Draft",

            "facility": saved_facility,
            "period": saved_period,
            "industry_name": industry_name,
            "subsector_id": subsector_id,
            "subsector_name": subsector_name,

            "configuration": configuration,

            "calculation_version": CALCULATION_VERSION,
            "emissions_unit": EMISSIONS_UNIT,

            "totals": {
                "scope_1": 0.0,
                "scope_2": 0.0,
                "scope_3": 0.0
            },

            "created_at": now,
            "updated_at": now
        }

        report_ref.set(report_payload)

        return jsonify({
            "success": True,
            "report_id": report_id,
            "report_name": report_name,
            "status": "Draft",
            "configuration": configuration,
            "calculation_ready": calculation_ready,
            "dataset_available": source_dataset_available,
            "factor_selection_required": True,
            # Deprecated: approved mappings are no longer required.
            # Kept so existing clients that read the key do not break.
            "approved_activity_count": 0,
            "message": (
                (
                    f"Dataset {selected_dataset_id} is pinned to this "
                    "report. Select a specific factor_id for each "
                    "activity; it is validated against this dataset "
                    "release before calculation."
                )
                if calculation_ready
                else (
                    "The report was created, but no matching imported "
                    "dataset is available."
                )
            )
        }), 201

    except ValueError as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except Exception:
        logger.exception("Failed to create carbon audit report")

        return jsonify({
            "success": False,
            "error": "Unable to create the report."
        }), 500


# ============================================================
# 10. REPORT LIST / DETAIL APIs
# ============================================================

def _report_totals(report_data):
    stored = report_data.get("totals") or {}
    s1 = to_finite_number(stored.get("scope_1", 0))
    s2 = to_finite_number(stored.get("scope_2", 0))
    s3 = to_finite_number(stored.get("scope_3", 0))
    return {
        "scope_1": s1,
        "scope_2": s2,
        "scope_3": s3,
        "total": round(s1 + s2 + s3, 6),
        "total_tco2e": round(s1 + s2 + s3, 6)
    }


def _report_list_item(snapshot):
    data = snapshot.to_dict() or {}
    configuration = data.get("configuration") or {}
    totals = _report_totals(data)
    return {
        "report_id": data.get("report_id", snapshot.id),
        "report_name": data.get("report_name", "Untitled audit"),
        "status": data.get("status", "Draft"),
        "facility": data.get("facility") or {},
        "period": data.get("period") or {},
        "industry_id": configuration.get("industry_id"),
        "industry_name": data.get("industry_name") or configuration.get("industry_id"),
        "subsector_id": data.get("subsector_id"),
        "subsector_name": data.get("subsector_name", ""),
        "configuration": configuration,
        "totals": totals,
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "calculation_version": data.get("calculation_version", "legacy"),
        "emissions_unit": data.get("emissions_unit", EMISSIONS_UNIT)
    }


@app.get("/api/reports")
def list_reports():
    """List saved reports from Firestore, newest first (MVP pagination)."""
    try:
        try:
            limit = int(request.args.get("limit", "50"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "limit must be an integer."}), 400

        if not 1 <= limit <= 100:
            return jsonify({"success": False, "error": "limit must be between 1 and 100."}), 400

        snapshots = list(db.collection("reports").stream())
        items = [_report_list_item(snapshot) for snapshot in snapshots]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        has_more = len(items) > limit
        items = items[:limit]
        return jsonify({
            "success": True,
            "count": len(items),
            "limit": limit,
            "has_more": has_more,
            "reports": items
        }), 200
    except Exception:
        logger.exception("Failed to list carbon audit reports")
        return jsonify({"success": False, "error": "Unable to retrieve reports."}), 500


@app.get("/api/reports/<report_id>")
def get_report_detail(report_id):
    """Return saved report metadata and its persisted activity entries."""
    if not valid_report_id(report_id):
        return jsonify({"success": False, "error": "A valid report_id is required."}), 400

    try:
        report_ref = db.collection("reports").document(report_id)
        report_snapshot = report_ref.get()
        if not report_snapshot.exists:
            return jsonify({"success": False, "error": "Report not found."}), 404

        data = report_snapshot.to_dict() or {}
        report = _report_list_item(report_snapshot)
        entries = []
        for entry_snapshot in report_ref.collection("entries").stream():
            entry = entry_snapshot.to_dict() or {}
            entry["entry_id"] = entry.get("entry_id", entry_snapshot.id)
            entries.append(entry)

        entries.sort(key=lambda item: str(
            (item.get("audit_trail") or {}).get("created_at") or ""
        ))
        report["entries"] = entries
        report["raw_report"] = data
        return jsonify({"success": True, "report": report}), 200
    except Exception:
        logger.exception("Failed to retrieve report details")
        return jsonify({"success": False, "error": "Unable to retrieve report details."}), 500


# ============================================================
# 11. REPORT SUMMARY API
# ============================================================

def report_summary_response(report_id):
    if not valid_report_id(report_id):
        return jsonify({
            "success": False,
            "error": "A valid report_id is required."
        }), 400

    report_ref = (
        db.collection("reports")
        .document(report_id)
    )

    report_snap = report_ref.get()

    if not report_snap.exists:
        return jsonify({
            "success": True,
            "report_id": report_id,
            "report_exists": False,
            "status": "Draft",
            "emissions_unit": EMISSIONS_UNIT,
            "totals": {
                "scope_1": 0.0,
                "scope_2": 0.0,
                "scope_3": 0.0,
                "total": 0.0,
                "total_tco2e": 0.0,
                "scope_1_tco2e": 0.0,
                "scope_2_tco2e": 0.0,
                "scope_3_tco2e": 0.0
            }
        }), 200

    report_data = report_snap.to_dict() or {}
    stored_totals = report_data.get("totals") or {}

    scope_1 = to_finite_number(
        stored_totals.get("scope_1", 0)
    )
    scope_2 = to_finite_number(
        stored_totals.get("scope_2", 0)
    )
    scope_3 = to_finite_number(
        stored_totals.get("scope_3", 0)
    )

    total = scope_1 + scope_2 + scope_3

    return jsonify({
        "success": True,
        "report_id": report_id,
        "report_exists": True,
        "report_name": report_data.get("report_name"),
        "status": report_data.get("status", "Draft"),

        "configuration": report_data.get("configuration"),

        "calculation_version": report_data.get(
            "calculation_version",
            "legacy"
        ),

        "emissions_unit": report_data.get(
            "emissions_unit",
            EMISSIONS_UNIT
        ),

        "totals": {
            "scope_1": scope_1,
            "scope_2": scope_2,
            "scope_3": scope_3,

            "total": round(total, 6),
            "total_tco2e": round(total, 6),

            "scope_1_tco2e": scope_1,
            "scope_2_tco2e": scope_2,
            "scope_3_tco2e": scope_3
        }
    }), 200


@app.get("/api/reports/<report_id>/summary")
def get_report_summary(report_id):
    try:
        return report_summary_response(report_id)

    except Exception:
        logger.exception("Failed to retrieve report summary")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve report metrics."
        }), 500


# Backward-compatible GET URL.
@app.get("/api/calculate-and-log")
def get_calculation_summary():
    try:
        report_id = request.args.get("report_id", "").strip()

        if not report_id:
            return jsonify({
                "success": False,
                "error": "The report_id query parameter is required."
            }), 400

        return report_summary_response(report_id)

    except Exception:
        logger.exception("Failed to retrieve calculation summary")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve report metrics."
        }), 500


# ============================================================
# 11. GWP LOOKUP
# ============================================================

def find_gwp_value(gwp_basis, gas):
    """
    Resolve a gas GWP from the imported, selected GWP dataset.
    No numeric GWP values are embedded in Python.
    """

    if gwp_basis == "source_defined":
        raise ValueError(
            "This activity produces individual gas mass, but the report "
            "uses source_defined GWP. Select an available IPCC GWP basis "
            "and load its GWP dataset."
        )

    matching = [
        row for row in load_gwp_rows()
        if (
            row["gwp_basis"] == gwp_basis
            and row["gas"].upper() == gas.upper()
        )
    ]

    if not matching:
        raise ValueError(
            f"No GWP value is available for gas '{gas}' under "
            f"'{gwp_basis}'. No default GWP was substituted."
        )

    distinct_values = {
        row["gwp_value"] for row in matching
    }

    if len(distinct_values) != 1:
        raise ValueError(
            f"Multiple conflicting GWP values were found for gas "
            f"'{gas}' under '{gwp_basis}'. Resolve the dataset versions "
            "before calculating."
        )

    return matching[0]


# ============================================================
# 12. FACTOR LOOKUP AND EMISSIONS CALCULATION
# ============================================================



def calculate_activity_emissions(
    configuration,
    process_id,
    activity_id,
    selected_unit,
    raw_value,
    factor_id=None,
    expected_scope=None,
    expected_dataset_id=None,
    expected_release=None
):
    """
    Calculate from one explicitly selected, imported Firestore factor.

    process_id and activity_id are report metadata only. They do not
    select, filter or unlock a factor, so predefined and user-defined
    names behave identically. The factor is validated against the
    report's pinned dataset release, geography, unit, scope and output
    type; the optional expected_* arguments let the caller assert what
    the user saw when choosing the factor.

    Initially supports aggregate DEFRA factors expressed as
    kg CO2e per activity unit. Component factors and unverified
    zero/missing factors are rejected.
    """

    if not factor_id:
        raise LookupError(
            "No applicable factor: select a specific factor_id "
            "before calculating."
        )

    if (
        isinstance(raw_value, bool)
        or not isinstance(raw_value, (int, float))
        or not math.isfinite(raw_value)
        or raw_value < 0
    ):
        raise ValueError(
            "raw_value must be a finite, non-negative number."
        )

    if not isinstance(selected_unit, str) or not selected_unit.strip():
        raise ValueError("selected_unit is required.")

    source_id = configuration.get("factor_source_id")
    dataset_year = configuration.get("factor_dataset_year")
    geography = str(
        configuration.get("geography", "")
    ).strip()

    if source_id != "defra_desnz":
        raise LookupError(
            "This calculation path currently supports the imported "
            "DEFRA dataset only. No other source is substituted."
        )

    # DEFRA's UK reporting dataset must not silently be used for
    # an activity configured for another geography.
    if geography.casefold() != "uk":
        raise LookupError(
            "The selected DEFRA dataset is for UK reporting. "
            "Choose a supported UK profile or import an appropriate "
            "factor dataset for the selected geography."
        )

    try:
        dataset_year = int(dataset_year)
    except (TypeError, ValueError):
        raise ValueError(
            "The report must specify a valid factor dataset year."
        )

    # Retrieve the exact dataset release pinned to the report.
    dataset_id = str(
        configuration.get("factor_dataset_id") or ""
    ).strip()

    if not dataset_id:
        raise LookupError(
            "The report has no pinned factor dataset release. "
            "Create a new configured report before calculating."
        )

    dataset_snapshot = (
        db.collection("factor_datasets")
        .document(dataset_id)
        .get()
    )

    if not dataset_snapshot.exists:
        raise LookupError(
            "The report's pinned factor dataset no longer exists."
        )

    dataset_metadata = dataset_snapshot.to_dict() or {}

    if dataset_metadata.get("import_status") != "imported":
        raise LookupError(
            "The report's pinned dataset is not fully imported."
        )

    try:
        registered_year = int(dataset_metadata.get("dataset_year"))
    except (TypeError, ValueError):
        raise LookupError(
            "The pinned dataset has an invalid dataset year."
        )

    if (
        dataset_metadata.get("source_id") != source_id
        or registered_year != dataset_year
        or str(dataset_metadata.get("source_release"))
        != str(configuration.get("factor_dataset_release"))
        or str(dataset_metadata.get("geography") or "").casefold()
        != geography.casefold()
    ):
        raise LookupError(
            "The pinned dataset does not match the report's "
            "source, year, release or geography."
        )

    if expected_dataset_id and expected_dataset_id != dataset_snapshot.id:
        raise LookupError(
            "The selected factor was offered from a different dataset "
            "than the one pinned to this report."
        )

    if (
        expected_release
        and str(expected_release)
        != str(dataset_metadata.get("source_release"))
    ):
        raise LookupError(
            "The selected factor's dataset release does not match the "
            "release pinned to this report."
        )

    factor_snapshot = (
        dataset_snapshot.reference
        .collection("factors")
        .document(factor_id)
        .get()
    )

    if not factor_snapshot.exists:
        raise LookupError(
            "The selected factor ID was not found in the chosen dataset."
        )

    factor = factor_snapshot.to_dict() or {}

    # Confirm that the selected factor belongs to this exact dataset.
    if (
        factor.get("dataset_id") != dataset_snapshot.id
        or factor.get("source_id") != source_id
        or factor.get("dataset_year") != dataset_year
        or str(factor.get("source_release"))
        != str(dataset_metadata.get("source_release"))
    ):
        raise LookupError(
            "The factor does not belong to the report's "
            "selected dataset release."
        )

    if factor.get("factor_status") != "present":
        raise LookupError(
            "This factor is missing, zero-valued pending review, "
            "or otherwise unavailable for calculation."
        )

    factor_value = factor.get("factor_value")

    # Same rule as GET /api/factors and the mapping workflow: a factor
    # must be a finite, positive number even if its status is "present".
    if (
        isinstance(factor_value, bool)
        or not isinstance(factor_value, (int, float))
        or not math.isfinite(factor_value)
        or factor_value <= 0
    ):
        raise LookupError(
            "The selected factor has no valid positive numeric value."
        )

    if factor.get("activity_unit") != selected_unit:
        raise ValueError(
            f"The factor uses '{factor.get('activity_unit')}', "
            f"but the submitted activity uses '{selected_unit}'. "
            "Choose a matching unit or an explicitly supported "
            "unit conversion."
        )

    # This initial implementation uses only a complete aggregate
    # CO2e factor. Gas-component rows must not be treated as totals.
    ghg_unit = str(factor.get("ghg_unit", "")).strip().casefold()

    if ghg_unit != "kg co2e":
        raise LookupError(
            "This record is not a complete aggregate 'kg CO2e' "
            "factor. Component factors require a separate, validated "
            "calculation method and cannot be used as a total."
        )

    if configuration.get("gwp_basis") != "source_defined":
        raise LookupError(
            "This factor is already expressed as CO2e using the "
            "source's published basis. Select source_defined rather "
            "than applying a different GWP basis a second time."
        )

    scope_number = factor.get("scope_number")

    if scope_number not in (1, 2, 3):
        raise LookupError(
            "The selected source factor has no valid scope classification."
        )

    if expected_scope is not None and expected_scope != scope_number:
        raise LookupError(
            f"The factor is a Scope {scope_number} factor, but Scope "
            f"{expected_scope} was requested."
        )

    # Source factors are kg CO2e per activity unit. Use Decimal so the
    # kg -> t conversion does not add binary floating-point noise.
    calculated_decimal = (
        Decimal(str(raw_value)) * Decimal(str(factor_value)) / Decimal(1000)
    )
    calculated_tco2e = float(calculated_decimal)

    if not math.isfinite(calculated_tco2e):
        raise ValueError(
            "The emissions calculation produced an invalid result."
        )

    factor_detail = {
        "factor_id": factor_id,
        "source_id": source_id,
        "source_name": factor.get("source_name"),
        "source_release": factor.get("source_release"),
        "source_url": factor.get("source_url"),
        "dataset_id": dataset_snapshot.id,
        "dataset_year": dataset_year,
        "dataset_release": dataset_metadata.get("source_release"),
        "geography": dataset_metadata.get("geography"),

        # Provenance of the applicability decision: the user chose this
        # exact factor; no approved mapping was consulted.
        "selection_basis": "explicit_factor_selection",

        "factor_value": factor_value,
        "activity_unit": factor.get("activity_unit"),
        "factor_output_unit": "kgCO2e",

        "ghg_unit": factor.get("ghg_unit"),
        "gwp_basis": "source_defined",
        "scope": scope_number,

        "category_level_1": factor.get("category_level_1"),
        "category_level_2": factor.get("category_level_2"),
        "category_level_3": factor.get("category_level_3"),
        "category_level_4": factor.get("category_level_4"),
        "column_text": factor.get("column_text"),

        "component_tco2e": round(calculated_tco2e, 9)
    }

    return {
        "calculated_tco2e": round(calculated_tco2e, 6),
        "scope": scope_number,
        "factor_details": [factor_detail]
    }



# ============================================================
# 13. POST: CALCULATE AND SAVE AN AUDIT ENTRY
# ============================================================

@app.post("/api/calculate-and-log")
def calculate_and_log():
    try:
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "A valid JSON request body is required."
            }), 400

        report_id = str(
            data.get("report_id", "")
        ).strip()

        if not valid_report_id(report_id):
            return jsonify({
                "success": False,
                "error": "A valid report_id is required."
            }), 400

        try:
            if isinstance(data.get("raw_value"), bool):
                raise ValueError
            raw_value = float(data.get("raw_value"))
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": "raw_value must be numeric."
            }), 400

        if not math.isfinite(raw_value) or raw_value < 0:
            return jsonify({
                "success": False,
                "error": (
                    "raw_value must be finite and non-negative."
                )
            }), 400

        # Process and activity are optional labels (predefined or
        # user-defined). They are stored as metadata and never used to
        # find or authorise a factor.
        process_name = clean_label(
            data.get("process_name"), "process_name"
        )
        activity_name = clean_label(
            data.get("activity_name"), "activity_name"
        )
        process_id = clean_label(
            data.get("process_id"), "process_id"
        ) or process_name
        activity_id = clean_label(
            data.get("activity_id"), "activity_id"
        ) or activity_name

        selected_unit = str(
            data.get("selected_unit", "")
        ).strip()

        factor_id = str(data.get("factor_id", "")).strip()

        if not selected_unit or not factor_id:
            return jsonify({
                "success": False,
                "error": "selected_unit and factor_id are required.",
                "error_code": "NO_APPLICABLE_FACTOR"
            }), 400

        # Optional assertions about the factor the user was shown.
        expected_scope = parse_scope_filter(data.get("scope"))
        expected_dataset_id = str(
            data.get("dataset_id") or ""
        ).strip()
        expected_release = str(
            data.get("dataset_release") or ""
        ).strip()

        report_ref = (
            db.collection("reports")
            .document(report_id)
        )

        report_snap = report_ref.get()

        if not report_snap.exists:
            return jsonify({
                "success": False,
                "error": (
                    "Report not found. Create and configure a report "
                    "before recording activities."
                )
            }), 404

        report_data = report_snap.to_dict() or {}

        # Old demo reports are readable but cannot receive new
        # calculations without a proper methodology configuration.
        if (
            report_data.get("calculation_version")
            != CALCULATION_VERSION
        ):
            return jsonify({
                "success": False,
                "error": (
                    "This report was created using the previous demo "
                    "calculation version. Create a new configured report "
                    "before adding data through the standards-driven "
                    "calculation engine."
                )
            }), 409

        configuration = report_data.get("configuration")

        if not isinstance(configuration, dict):
            return jsonify({
                "success": False,
                "error": "The report has no calculation configuration."
            }), 409

        # Financed emissions do not use the general activity-factor
        # equation. They need asset-class-specific attribution inputs
        # and a configured PCAF method. The guard keys on the selected
        # methodology, not on an industry label.
        if configuration.get("accounting_framework") == "pcaf":
            return jsonify({
                "success": False,
                "error": (
                    "Financed emissions require a PCAF asset-class "
                    "calculation and borrower/investee financial data. "
                    "The generic activity-factor formula is not valid "
                    "for this activity. That calculation path must be "
                    "configured separately."
                )
            }), 422

        calculated = calculate_activity_emissions(
            configuration=configuration,
            process_id=process_id,
            activity_id=activity_id,
            selected_unit=selected_unit,
            raw_value=raw_value,
            factor_id=factor_id,
            expected_scope=expected_scope,
            expected_dataset_id=expected_dataset_id or None,
            expected_release=expected_release or None
        )

        calculated_tco2e = calculated["calculated_tco2e"]
        scope_number = calculated["scope"]

        entry_id = str(uuid.uuid4())
        created_at = utc_timestamp()

        user_name = str(
            data.get("user_name", "Audit User")
        ).strip()

        entry_payload = {
            "entry_id": entry_id,
            "report_id": report_id,

            "industry_id": configuration.get("industry_id"),
            "industry_name": report_data.get("industry_name", ""),
            "reporting_year": configuration["reporting_year"],

            "process_id": process_id,
            "process_name": process_name,
            "activity_id": activity_id,
            "activity_name": activity_name,

            "raw_value": raw_value,
            "selected_unit": selected_unit,

            "scope": scope_number,

            "calculated_tco2e": calculated_tco2e,
            "emissions_unit": EMISSIONS_UNIT,

            "factor_source_id": configuration["factor_source_id"],
            "factor_dataset_year": configuration["factor_dataset_year"],
            "geography": configuration["geography"],
            "gwp_basis": configuration["gwp_basis"],
            "accounting_framework": configuration[
                "accounting_framework"
            ],

            # Exact provenance for reproducibility.
            "factor_details": calculated["factor_details"],

            "commentary": data.get("commentary", ""),

            "evidence": {
                "declaration": data.get("declaration", ""),
                "reference": data.get("evidence_reference", "")
            },

            "audit_trail": {
                "created_by": user_name,
                "created_at": created_at
            },

            "calculation_version": CALCULATION_VERSION
        }

        transaction = db.transaction()

        report_entry_ref = (
            report_ref
            .collection("entries")
            .document(entry_id)
        )

        @firestore.transactional
        def save_entry(transaction):
            current_snapshot = report_ref.get(
                transaction=transaction
            )

            if not current_snapshot.exists:
                raise ValueError("Report no longer exists.")

            current_report = current_snapshot.to_dict() or {}

            if current_report.get("status", "Draft") != "Draft":
                raise ValueError(
                    "Only Draft reports can be modified."
                )

            if (
                current_report.get("calculation_version")
                != CALCULATION_VERSION
            ):
                raise ValueError(
                    "The report calculation version changed. "
                    "Create a new report before recording this activity."
                )

            if current_report.get("configuration") != configuration:
                raise ValueError(
                    "The report configuration changed during calculation. "
                    "Reload the report and try again."
                )

            stored_totals = current_report.get("totals") or {}

            scope_field = f"scope_{scope_number}"

            current_total = to_finite_number(
                stored_totals.get(scope_field, 0)
            )

            new_scope_total = round(
                current_total + calculated_tco2e,
                6
            )

            transaction.update(
                report_ref,
                {
                    f"totals.{scope_field}": new_scope_total,
                    "updated_at": created_at
                }
            )

            transaction.set(
                report_entry_ref,
                entry_payload
            )

        save_entry(transaction)

        return jsonify({
            "success": True,
            "report_id": report_id,
            "entry_id": entry_id,

            "process_id": process_id,
            "process_name": process_name,
            "activity_id": activity_id,
            "activity_name": activity_name,

            "raw_value": raw_value,
            "selected_unit": selected_unit,

            "scope": scope_number,

            "calculated_tco2e": calculated_tco2e,
            "emissions_unit": EMISSIONS_UNIT,

            "calculation_version": CALCULATION_VERSION,

            "factor_details": calculated["factor_details"]
        }), 200

    except LookupError as error:
        return jsonify({
            "success": False,
            "error": str(error),
            "error_code": "NO_APPLICABLE_FACTOR"
        }), 422

    except ValueError as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except Exception:
        logger.exception(
            "Failed to calculate and save carbon audit entry"
        )

        return jsonify({
            "success": False,
            "error": (
                "Unable to calculate and save the audit entry."
            )
        }), 500


# ============================================================
# 14. START FLASK
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=(
            os.environ.get(
                "FLASK_DEBUG",
                "false"
            ).lower() == "true"
        ),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001))
    )