import csv
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


BASE_DIR = Path(__file__).resolve().parent

SOURCE_XLSX_FILE = (
    BASE_DIR
    / "data"
    / "source"
    / "ghg-conversion-factors-2026-flat-format-revised.xlsx"
)

CSV_FILE = (
    BASE_DIR
    / "data"
    / "source"
    / "defra_2026_factors_normalized.csv"
)

SERVICE_ACCOUNT_FILE = BASE_DIR / "carbon-audit-service-account.json"

DATASET_GEOGRAPHY = "UK"

BATCH_SIZE = 400


def utc_now():
    return datetime.now(timezone.utc).isoformat()

def sha256_file(path):
    """Calculate a file's SHA-256 checksum without loading it all into memory."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def initialize_firestore():
    if not firebase_admin._apps:
        if not SERVICE_ACCOUNT_FILE.is_file():
            raise FileNotFoundError(
                f"Firebase credentials not found: {SERVICE_ACCOUNT_FILE}"
            )

        cred = credentials.Certificate(str(SERVICE_ACCOUNT_FILE))
        firebase_admin.initialize_app(cred)

    return firestore.client()


def parse_scope_number(value):
    value = (value or "").strip()

    if value in {"1", "2", "3"}:
        return int(value)

    return None


def convert_factor_value(row):
    """
    Preserve the original factor text.
    A missing value remains null; it is never changed to zero.
    """

    raw_value = (row.get("factor_value") or "").strip()
    status = (row.get("factor_status") or "").strip()

    if not raw_value:
        return None, status or "missing"

    try:
        return float(raw_value), status
    except (TypeError, ValueError):
        return None, "non_numeric"


def main():
    if not CSV_FILE.is_file():
        raise FileNotFoundError(
            "Normalized DEFRA CSV not found:\n"
            f"{CSV_FILE}"
        )

    if not SOURCE_XLSX_FILE.is_file():
        raise FileNotFoundError(
            "Original DEFRA source workbook not found:\n"
            f"{SOURCE_XLSX_FILE}"
    )
    if not SERVICE_ACCOUNT_FILE.is_file():
        raise FileNotFoundError(
            "Firebase credentials not found:\n"
            f"{SERVICE_ACCOUNT_FILE}"
        )

    with CSV_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if not rows:
        raise ValueError("The normalized DEFRA CSV contains no records.")

    required_columns = {
        "source_id",
        "source_name",
        "source_url",
        "source_release",
        "dataset_year",
        "factor_id",
        "scope_label",
        "scope_number",
        "category_level_1",
        "category_level_2",
        "category_level_3",
        "category_level_4",
        "column_text",
        "activity_unit",
        "ghg_unit",
        "factor_value",
        "factor_status",
    }

    missing = required_columns - set(rows[0].keys())

    if missing:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing)}"
        )

    source_id = rows[0]["source_id"].strip()
    dataset_year = rows[0]["dataset_year"].strip()
    source_release = rows[0]["source_release"].strip()

    if not source_id or not dataset_year or not source_release:
        raise ValueError(
            "The source ID, dataset year or release is missing."
        )

    if any(
        row["source_id"].strip() != source_id
        or row["dataset_year"].strip() != dataset_year
        or row["source_release"].strip() != source_release
        for row in rows
    ):
        raise ValueError(
            "The CSV contains multiple dataset identities. "
            "Import one source/version at a time."
        )

    factor_ids = [
        row["factor_id"].strip()
        for row in rows
    ]

    if any(not factor_id for factor_id in factor_ids):
        raise ValueError("At least one factor record has no source ID.")

    if len(factor_ids) != len(set(factor_ids)):
        raise ValueError(
            "Duplicate factor IDs found. Resolve them before importing."
        )

    dataset_id = (
        f"{source_id}_{dataset_year}_v"
        f"{source_release.replace('.', '_')}"
    )

    db = initialize_firestore()

    dataset_ref = (
        db.collection("factor_datasets")
        .document(dataset_id)
    )

    factors_ref = dataset_ref.collection("factors")

    started_at = utc_now()

    # This metadata describes the dataset; it contains no invented factors.
    dataset_ref.set({
        "dataset_id": dataset_id,
        "source_id": source_id,
        "source_name": rows[0]["source_name"],
        "source_url": rows[0]["source_url"],
        "source_release": source_release,
        "dataset_year": int(dataset_year),
        "imported_from": CSV_FILE.name,
        "source_updated_at": rows[0].get("source_updated_at", ""),
        "geography": DATASET_GEOGRAPHY,

        "source_file_name": SOURCE_XLSX_FILE.name,
        "source_file_sha256": sha256_file(SOURCE_XLSX_FILE),

        "normalized_file_name": CSV_FILE.name,
        "normalized_file_sha256": sha256_file(CSV_FILE),
        "record_count_expected": len(rows),
        "import_status": "importing",
        "import_started_at": started_at,
        "schema_version": "raw-source-factor-v1",
        "applicability_note": (
            "Preserves published source records. Geographic and "
            "activity applicability must be established from the "
            "source documentation and reviewed mappings."
        )
    }, merge=True)

    print(f"Dataset: {dataset_id}")
    print(f"Source records: {len(rows)}")
    print("Importing records into Firestore...")

    status_counts = {}
    imported_count = 0

    for start in range(0, len(rows), BATCH_SIZE):
        batch = db.batch()
        chunk = rows[start:start + BATCH_SIZE]

        for row in chunk:
            factor_id = row["factor_id"].strip()
            factor_value, factor_status = convert_factor_value(row)

            document = {
                "factor_id": factor_id,
                "dataset_id": dataset_id,

                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "source_url": row["source_url"],
                "source_release": row["source_release"],
                "source_updated_at": row.get("source_updated_at", ""),
                "dataset_year": int(row["dataset_year"]),

                # Original published category structure
                "scope_label": row["scope_label"],
                "scope_number": parse_scope_number(
                    row["scope_number"]
                ),
                "category_level_1": row["category_level_1"],
                "category_level_2": row["category_level_2"],
                "category_level_3": row["category_level_3"],
                "category_level_4": row["category_level_4"],
                "column_text": row["column_text"],
                "activity_unit": row["activity_unit"],
                "ghg_unit": row["ghg_unit"],

                # Keep both a numeric value and the source text.
                "factor_value": factor_value,
                "factor_value_raw": row["factor_value"],
                "factor_status": factor_status,

                "source_data_unchanged": True
            }

            document_ref = factors_ref.document(factor_id)
            batch.set(document_ref, document, merge=True)

            status_counts[factor_status] = (
                status_counts.get(factor_status, 0) + 1
            )

        batch.commit()
        imported_count += len(chunk)

        print(f"Imported {imported_count}/{len(rows)} records")

    completed_at = utc_now()

    dataset_ref.set({
        "import_status": "imported",
        "record_count_imported": imported_count,
        "factor_status_counts": status_counts,
        "import_completed_at": completed_at
    }, merge=True)

    print("\nIMPORT COMPLETE")
    print(f"Dataset ID: {dataset_id}")
    print(f"Records written: {imported_count}")
    print(f"Status counts: {status_counts}")
    print(
        "Firestore path: "
        f"factor_datasets/{dataset_id}/factors/"
    )


if __name__ == "__main__":
    main()
