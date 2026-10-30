import uuid

from app import app, db


client = app.test_client()

# Create a unique test report; existing reports are untouched.
report_id = f"E2E_NATURAL_GAS_{uuid.uuid4().hex[:10].upper()}"

report_payload = {
    "report_id": report_id,
    "report_name": "End-to-End Natural Gas Calculation Test",
    "industry_id": "power_generation",
    "reporting_year": 2026,
    "factor_source_id": "defra_desnz",
    "factor_dataset_year": 2026,
    "geography": "UK",
    "gwp_basis": "source_defined",
    "accounting_framework": "ghg_protocol_corporate",
}

print("\n1. CREATE TEST REPORT")

response = client.post("/api/reports", json=report_payload)
report_result = response.get_json() or {}

print("HTTP status:", response.status_code)
print("Response:", report_result)

if response.status_code != 201:
    raise SystemExit("Report creation failed. Calculation not attempted.")

print("\n2. CALCULATE EMISSIONS")

calculation_payload = {
    "report_id": report_id,
    "process_id": "fuel_combustion",
    "activity_id": "natural_gas_consumption",
    "selected_unit": "cubic metres",
    "raw_value": 100,
    "factor_id": "1_100_1004_1_1",
    "user_name": "End-to-End Test",
}

response = client.post(
    "/api/calculate-and-log",
    json=calculation_payload,
)
result = response.get_json() or {}

print("HTTP status:", response.status_code)
print("Response:", result)

if response.status_code != 200 or not result.get("success"):
    raise SystemExit(
        "Calculation failed. A draft test report may remain in Firestore."
    )

expected_tco2e = 0.202633
actual_tco2e = result.get("calculated_tco2e")

if actual_tco2e != expected_tco2e:
    raise SystemExit(
        f"Incorrect result: {actual_tco2e}; expected {expected_tco2e}"
    )

print("\n3. VERIFY SAVED FIRESTORE RECORDS")

report_ref = db.collection("reports").document(report_id)
report_snapshot = report_ref.get()
report = report_snapshot.to_dict() or {}

entry_id = result["entry_id"]
entry_snapshot = (
    report_ref.collection("entries").document(entry_id).get()
)
entry = entry_snapshot.to_dict() or {}

print("Report exists:", report_snapshot.exists)
print("Entry exists:", entry_snapshot.exists)
print("Report ID:", report_id)
print("Entry ID:", entry_id)
print("Scope 1 total:", (report.get("totals") or {}).get("scope_1"))
print("Saved calculation:", entry.get("calculated_tco2e"))
print("Saved factor source:", entry.get("factor_source_id"))
print("Saved factor year:", entry.get("factor_dataset_year"))
print(
    "Saved factor ID:",
    (entry.get("factor_details") or [{}])[0].get("factor_id"),
)

assert report_snapshot.exists
assert entry_snapshot.exists
assert (report.get("totals") or {}).get("scope_1") == expected_tco2e
assert entry.get("calculated_tco2e") == expected_tco2e
assert entry.get("scope") == 1
assert entry.get("factor_source_id") == "defra_desnz"
assert (
    entry.get("factor_details") or [{}]
)[0].get("factor_id") == "1_100_1004_1_1"

print("\nSUCCESS: End-to-end calculation verified.")