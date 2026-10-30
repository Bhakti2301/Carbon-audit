
import uuid

from app import app, db


# Previously verified, release-pinned test report.
REPORT_ID = "E2E_NATURAL_GAS_5C020FFD4B"
DATASET_ID = "defra_desnz_2026_v1_2"

client = app.test_client()

report_ref = db.collection("reports").document(REPORT_ID)
report_snapshot = report_ref.get()

if not report_snapshot.exists:
    raise RuntimeError(
        f"Existing successful test report not found: {REPORT_ID}"
    )

report = report_snapshot.to_dict() or {}
configuration = report.get("configuration") or {}

if configuration.get("factor_dataset_id") != DATASET_ID:
    raise RuntimeError(
        "The test report does not pin the expected dataset."
    )

# Record existing entry IDs so we can prove rejected requests
# did not create new calculation entries.
entries_before = {
    snapshot.id
    for snapshot in report_ref.collection("entries").stream()
}

base_payload = {
    "report_id": REPORT_ID,
    "process_id": "fuel_combustion",
    "activity_id": "natural_gas_consumption",
    "selected_unit": "cubic metres",
    "raw_value": 100,
    "factor_id": "1_100_1004_1_1",
}


def check_rejected_calculation(name, payload, expected_status):
    """Assert an invalid calculation request is rejected."""

    response = client.post(
        "/api/calculate-and-log",
        json=payload,
    )
    body = response.get_json() or {}

    print(f"\n{name}")
    print("HTTP status:", response.status_code)
    print("Response:", body)

    assert response.status_code == expected_status, (
        f"{name}: expected HTTP {expected_status}, "
        f"received HTTP {response.status_code}"
    )

    assert body.get("success") is False, (
        f"{name}: invalid request was not rejected."
    )


# ------------------------------------------------------------
# TEST 1: Reject an unsupported activity-unit label.
# ------------------------------------------------------------

wrong_unit = {
    **base_payload,
    "selected_unit": "m3",
}

check_rejected_calculation(
    "Incorrect activity unit",
    wrong_unit,
    400,
)


# ------------------------------------------------------------
# TEST 2: Reject a factor without a matching approved mapping.
# ------------------------------------------------------------

wrong_factor = {
    **base_payload,
    "factor_id": "1_101_1012_8_1",
    "selected_unit": "litres",
}

check_rejected_calculation(
    "Factor without a matching approved mapping",
    wrong_factor,
    422,
)


# ------------------------------------------------------------
# TEST 3: Reject unsupported geography at report creation.
# This must call /api/reports, NOT /api/calculate-and-log.
# ------------------------------------------------------------

invalid_report_id = (
    f"NEGATIVE_GEO_{uuid.uuid4().hex[:12].upper()}"
)

invalid_geography = {
    "report_id": invalid_report_id,
    "report_name": "Invalid Geography Negative Test",
    "industry_id": "power_generation",
    "reporting_year": 2026,
    "factor_source_id": "defra_desnz",
    "factor_dataset_year": 2026,
    "geography": "India",
    "gwp_basis": "source_defined",
    "accounting_framework": "ghg_protocol_corporate",
}

response = client.post(
    "/api/reports",
    json=invalid_geography,
)
body = response.get_json() or {}

print("\nUnsupported DEFRA geography")
print("HTTP status:", response.status_code)
print("Response:", body)

assert response.status_code == 422, (
    "Unsupported DEFRA geography: expected HTTP 422, "
    f"received HTTP {response.status_code}"
)

assert body.get("success") is False, (
    "The invalid-geography report was not rejected."
)

invalid_report_snapshot = (
    db.collection("reports")
    .document(invalid_report_id)
    .get()
)

assert not invalid_report_snapshot.exists, (
    "The invalid-geography report was unexpectedly saved."
)


# ------------------------------------------------------------
# FINAL CHECK: Rejected calculations did not create new entries.
# ------------------------------------------------------------

entries_after = {
    snapshot.id
    for snapshot in report_ref.collection("entries").stream()
}

if entries_after != entries_before:
    raise AssertionError(
        "Rejected requests unexpectedly changed the calculation entries."
    )

print("\nSUCCESS: All three guardrail tests passed.")
print("No extra calculation entries were created.")
print("The invalid-geography report was not saved.")
