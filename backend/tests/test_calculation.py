"""
Offline tests for the factor-driven calculation path.

Run from the carbon-audit directory:  python -m unittest discover -s tests -v

These tests use an in-memory fake Firestore (tests/fake_firestore.py).
They never connect to or write to a real Firestore project.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from fake_firestore import FakeDb, install_stubs  # noqa: E402

DB = FakeDb()
install_stubs(DB)

import app as backend  # noqa: E402

DATASET_ID = "defra_desnz_2026_1_2"
RELEASE = "1.2"


def dataset_doc(**overrides):
    doc = {
        "source_id": "defra_desnz",
        "source_name": "DEFRA/DESNZ",
        "source_release": RELEASE,
        "dataset_year": 2026,
        "geography": "UK",
        "import_status": "imported",
        "record_count_imported": 8740,
    }
    doc.update(overrides)
    return doc


def factor_doc(factor_id, **overrides):
    doc = {
        "factor_id": factor_id,
        "dataset_id": DATASET_ID,
        "source_id": "defra_desnz",
        "source_name": "DEFRA/DESNZ",
        "source_release": RELEASE,
        "source_url": "https://example.test/defra",
        "dataset_year": 2026,
        "scope_number": 1,
        "scope_label": "Scope 1",
        "category_level_1": "Fuels",
        "category_level_2": "Gaseous fuels",
        "category_level_3": "Natural gas",
        "category_level_4": "",
        "column_text": "kg CO2e",
        "activity_unit": "cubic metres",
        "ghg_unit": "kg CO2e",
        "factor_value": 2.02633,
        "factor_status": "present",
    }
    doc.update(overrides)
    return doc


REPORT_CONFIG = {
    "industry_id": "steel_manufacturing",
    "reporting_year": "2026",
    "factor_source_id": "defra_desnz",
    "factor_dataset_year": "2026",
    "factor_dataset_id": DATASET_ID,
    "factor_dataset_release": RELEASE,
    "geography": "UK",
    "gwp_basis": "source_defined",
    "accounting_framework": "ghg_protocol_corporate",
}


def seed():
    DB.docs.clear()
    DB.queries.clear()
    DB.put(("factor_datasets", DATASET_ID), dataset_doc())
    base = ("factor_datasets", DATASET_ID, "factors")
    DB.put(base + ("GAS_M3",), factor_doc("GAS_M3"))
    DB.put(base + ("GAS_KWH",), factor_doc(
        "GAS_KWH", activity_unit="kWh (Gross CV)", factor_value=0.18296))
    DB.put(base + ("ELEC_KWH",), factor_doc(
        "ELEC_KWH", scope_number=2, scope_label="Scope 2",
        category_level_1="UK electricity", category_level_3="",
        activity_unit="kWh", factor_value=0.20707))
    DB.put(base + ("ZERO",), factor_doc(
        "ZERO", factor_status="zero_requires_review", factor_value=0))
    DB.put(base + ("MISSING",), factor_doc(
        "MISSING", factor_status="missing", factor_value=None))
    DB.put(base + ("COMPONENT",), factor_doc(
        "COMPONENT", ghg_unit="kg CO2", factor_value=2.0))
    DB.put(base + ("STALE_REL",), factor_doc(
        "STALE_REL", source_release="1.1"))
    DB.put(base + ("OTHER_DS",), factor_doc(
        "OTHER_DS", dataset_id="some_other_dataset"))
    DB.put(("reports", "R1"), {
        "report_id": "R1", "report_name": "Test", "status": "Draft",
        "industry_name": "Steel", "configuration": dict(REPORT_CONFIG),
        "calculation_version": backend.CALCULATION_VERSION,
        "emissions_unit": "tCO2e",
        "totals": {"scope_1": 0.0, "scope_2": 0.0, "scope_3": 0.0},
    })


class Base(unittest.TestCase):
    def setUp(self):
        seed()
        backend.db = DB
        self.client = backend.app.test_client()

    def calc(self, **overrides):
        body = {
            "report_id": "R1", "factor_id": "GAS_M3",
            "selected_unit": "cubic metres", "raw_value": 100,
            "process_id": "melting", "activity_id": "natural_gas_consumption",
        }
        body.update(overrides)
        body = {k: v for k, v in body.items() if v is not None}
        return self.client.post("/api/calculate-and-log", json=body)

    def set_config(self, **changes):
        report = DB.docs[("reports", "R1")]
        report["configuration"].update(changes)

    def entries(self):
        return [d for p, d in DB.docs.items()
                if p[:3] == ("reports", "R1", "entries")]


class NaturalGasVerified(Base):
    def test_100_m3_gives_0_202633_tco2e(self):
        res = self.calc()
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertEqual(body["calculated_tco2e"], 0.202633)
        self.assertEqual(body["scope"], 1)
        detail = body["factor_details"][0]
        self.assertEqual(detail["factor_value"], 2.02633)
        self.assertEqual(detail["dataset_id"], DATASET_ID)
        self.assertEqual(detail["dataset_release"], RELEASE)
        self.assertEqual(detail["source_release"], RELEASE)
        self.assertEqual(detail["factor_output_unit"], "kgCO2e")

    def test_scope_total_log_and_summary_updated(self):
        self.calc()
        self.calc()
        self.assertEqual(len(self.entries()), 2)
        s = self.client.get("/api/reports/R1/summary").get_json()
        self.assertEqual(s["totals"]["scope_1"], 0.405266)
        self.assertEqual(s["totals"]["total_tco2e"], 0.405266)
        detail = self.client.get("/api/reports/R1").get_json()["report"]
        self.assertEqual(len(detail["entries"]), 2)
        self.assertEqual(detail["entries"][0]["factor_details"][0]
                         ["factor_id"], "GAS_M3")

    def test_factor_value_comes_from_store_not_request(self):
        DB.docs[("factor_datasets", DATASET_ID, "factors", "GAS_M3")][
            "factor_value"] = 3.0
        res = self.calc(factor_value=999)
        self.assertEqual(res.get_json()["calculated_tco2e"], 0.3)


class CustomNamesDoNotBlock(Base):
    def test_user_defined_process_and_activity(self):
        res = self.calc(process_id=None, activity_id=None,
                        process_name="Bespoke annealing line #7",
                        activity_name="Boiler gas (site B)")
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertEqual(body["calculated_tco2e"], 0.202633)
        self.assertEqual(body["process_name"], "Bespoke annealing line #7")
        saved = self.entries()[0]
        self.assertEqual(saved["process_id"], "Bespoke annealing line #7")
        self.assertEqual(saved["activity_name"], "Boiler gas (site B)")

    def test_process_and_activity_labels_are_optional(self):
        res = self.calc(process_id=None, activity_id=None)
        self.assertEqual(res.status_code, 200, res.get_json())

    def test_no_approved_mapping_exists_or_is_needed(self):
        self.assertFalse([p for p in DB.docs
                          if p[0] == "activity_factor_mappings"])
        self.assertEqual(self.calc().status_code, 200)

    def test_unknown_industry_report_can_calculate(self):
        self.set_config(industry_id="custom_recycling_plant")
        self.assertEqual(self.calc().status_code, 200)

    def test_overlong_label_rejected(self):
        res = self.calc(process_name="x" * 201)
        self.assertEqual(res.status_code, 400)


class Rejections(Base):
    def assert_rejected(self, res, status):
        self.assertEqual(res.status_code, status, res.get_json())
        self.assertFalse(res.get_json()["success"])
        self.assertEqual(self.entries(), [])
        totals = DB.docs[("reports", "R1")]["totals"]
        self.assertEqual(totals["scope_1"], 0.0)

    # dataset / release
    def test_report_pinned_release_differs_from_dataset(self):
        self.set_config(factor_dataset_release="1.1")
        self.assert_rejected(self.calc(), 422)

    def test_factor_from_other_release(self):
        self.assert_rejected(self.calc(factor_id="STALE_REL"), 422)

    def test_factor_from_other_dataset(self):
        self.assert_rejected(self.calc(factor_id="OTHER_DS"), 422)

    def test_client_asserts_wrong_release(self):
        self.assert_rejected(self.calc(dataset_release="1.1"), 422)

    def test_client_asserts_wrong_dataset(self):
        self.assert_rejected(self.calc(dataset_id="other"), 422)

    def test_no_pinned_dataset(self):
        self.set_config(factor_dataset_id=None)
        self.assert_rejected(self.calc(), 422)

    # geography / source
    def test_wrong_geography_on_report(self):
        self.set_config(geography="India")
        self.assert_rejected(self.calc(), 422)

    def test_dataset_geography_differs_from_report(self):
        DB.docs[("factor_datasets", DATASET_ID)]["geography"] = "EU"
        self.assert_rejected(self.calc(), 422)

    def test_unsupported_source(self):
        self.set_config(factor_source_id="ipcc_2006")
        self.assert_rejected(self.calc(), 422)

    # unit
    def test_unsupported_unit(self):
        self.assert_rejected(self.calc(selected_unit="litres"), 400)

    def test_unit_is_required(self):
        self.assert_rejected(self.calc(selected_unit=""), 400)

    # quantity
    def test_invalid_quantities(self):
        for bad in ("abc", "", None, True, -1, "nan", "inf", "-inf",
                    [1], {"v": 1}):
            with self.subTest(raw_value=bad):
                body = {"report_id": "R1", "factor_id": "GAS_M3",
                        "selected_unit": "cubic metres", "raw_value": bad}
                res = self.client.post("/api/calculate-and-log", json=body)
                self.assert_rejected(res, 400)

    # factor applicability
    def test_missing_factor_id(self):
        res = self.calc(factor_id="")
        self.assert_rejected(res, 400)
        self.assertEqual(res.get_json()["error_code"], "NO_APPLICABLE_FACTOR")

    def test_unknown_factor_id(self):
        res = self.calc(factor_id="DOES_NOT_EXIST")
        self.assert_rejected(res, 422)
        self.assertEqual(res.get_json()["error_code"], "NO_APPLICABLE_FACTOR")

    def test_zero_and_missing_factors(self):
        self.assert_rejected(self.calc(factor_id="ZERO"), 422)
        self.assert_rejected(self.calc(factor_id="MISSING"), 422)

    def test_component_gas_factor_not_a_total(self):
        self.assert_rejected(self.calc(factor_id="COMPONENT"), 422)

    def test_scope_mismatch_with_requested_scope(self):
        self.assert_rejected(self.calc(scope="Scope 2"), 422)
        self.assertEqual(self.calc(scope=1).status_code, 200)

    def test_invalid_scope_value(self):
        self.assert_rejected(self.calc(scope="7"), 400)

    def test_non_source_defined_gwp_basis(self):
        self.set_config(gwp_basis="ipcc_ar6")
        self.assert_rejected(self.calc(), 422)

    def test_unit_mismatch_for_selected_factor(self):
        self.assert_rejected(self.calc(factor_id="ELEC_KWH"), 400)

    def test_pcaf_framework_still_blocked(self):
        self.set_config(accounting_framework="pcaf")
        self.assert_rejected(self.calc(), 422)

    def test_non_draft_report_blocked(self):
        DB.docs[("reports", "R1")]["status"] = "Final"
        res = self.calc()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.entries(), [])


class EngineDirect(Base):
    def test_existing_positional_signature_still_works(self):
        out = backend.calculate_activity_emissions(
            dict(REPORT_CONFIG), "melting", "natural_gas_consumption",
            "cubic metres", 100, factor_id="GAS_M3")
        self.assertEqual(out["calculated_tco2e"], 0.202633)

    def test_engine_rejects_bad_quantity_directly(self):
        for bad in (float("nan"), float("inf"), -5, True):
            with self.assertRaises(ValueError):
                backend.calculate_activity_emissions(
                    dict(REPORT_CONFIG), "p", "a", "cubic metres", bad,
                    factor_id="GAS_M3")

    def test_engine_has_no_hardcoded_industry_or_process_ids(self):
        import inspect
        src = inspect.getsource(backend.calculate_activity_emissions)
        src += inspect.getsource(backend.calculate_and_log)
        for needle in ("banking_financial_services", "steel_manufacturing",
                       "activity_factor_mappings", "find_industry"):
            self.assertNotIn(needle, src)


class CandidateDiscovery(Base):
    def get(self, **params):
        params.setdefault("report_id", "R1")
        return self.client.get("/api/factors", query_string=params)

    def test_lists_only_pinned_dataset_valid_candidates(self):
        res = self.get(q="natural gas", unit="cubic metres")
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertEqual(body["dataset_id"], DATASET_ID)
        self.assertEqual(body["dataset_release"], RELEASE)
        ids = [f["factor_id"] for f in body["factors"]]
        self.assertIn("GAS_M3", ids)
        for excluded in ("ZERO", "MISSING", "COMPONENT"):
            self.assertNotIn(excluded, ids)

    def test_scope_filter(self):
        body = self.get(scope="2").get_json()
        self.assertEqual([f["factor_id"] for f in body["factors"]],
                         ["ELEC_KWH"])

    def test_filters_are_pushed_to_firestore(self):
        self.get(unit="cubic metres", scope="1")
        fields = {f for _, f, _ in DB.queries}
        self.assertIn("activity_unit", fields)
        self.assertIn("scope_number", fields)

    def test_unpinned_report_gets_clear_error(self):
        self.set_config(factor_dataset_id=None)
        res = self.get()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()["error_code"], "NO_PINNED_DATASET")

    def test_pinned_dataset_release_mismatch(self):
        self.set_config(factor_dataset_release="1.1")
        self.assertEqual(self.get().status_code, 409)

    def test_does_not_choose_a_factor(self):
        body = self.get().get_json()
        self.assertNotIn("selected_factor", body)
        self.assertIn("explicitly", body["mapping_note"])


class ReportCreation(Base):
    def create(self, **overrides):
        body = {
            "report_name": "R", "industry_id": "steel_manufacturing",
            "reporting_year": 2026, "factor_source_id": "defra_desnz",
            "factor_dataset_year": 2026, "geography": "UK",
            "gwp_basis": "source_defined",
            "accounting_framework": "ghg_protocol_corporate",
        }
        body.update(overrides)
        return self.client.post("/api/reports", json=body)

    def test_pins_dataset_id_and_release_and_is_ready(self):
        res = self.create(report_id="NEW1")
        self.assertEqual(res.status_code, 201, res.get_json())
        body = res.get_json()
        cfg = body["configuration"]
        self.assertEqual(cfg["factor_dataset_id"], DATASET_ID)
        self.assertEqual(cfg["factor_dataset_release"], RELEASE)
        self.assertTrue(body["calculation_ready"])

    def test_custom_industry_label_accepted(self):
        res = self.create(report_id="NEW2", industry_id="Boutique distillery",
                          industry_name="Boutique distillery")
        self.assertEqual(res.status_code, 201, res.get_json())

    def test_blank_industry_rejected(self):
        self.assertEqual(self.create(industry_id="  ").status_code, 400)

    def test_report_created_without_dataset_is_not_ready(self):
        DB.docs.pop(("factor_datasets", DATASET_ID))
        res = self.create(report_id="NEW3")
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.get_json()["calculation_ready"])
        self.assertIsNone(res.get_json()["configuration"]["factor_dataset_id"])

    def test_created_report_can_calculate_end_to_end(self):
        self.create(report_id="NEW4", industry_id="Anything at all")
        res = self.calc(report_id="NEW4", process_id="My own process")
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(res.get_json()["calculated_tco2e"], 0.202633)


class ReviewerWorkflowUnchanged(Base):
    def test_review_endpoints_still_require_token(self):
        self.assertEqual(
            self.client.get("/api/activity-factor-mappings").status_code, 503)
        backend.MAPPING_REVIEW_TOKEN = "secret-token"
        backend.MAPPING_REVIEWER_ID = "reviewer-1"
        try:
            self.assertEqual(
                self.client.get("/api/activity-factor-mappings").status_code,
                401)
            self.assertEqual(
                self.client.get(
                    "/api/activity-factor-mappings",
                    headers={"X-Mapping-Review-Token": "wrong"}).status_code,
                401)
        finally:
            backend.MAPPING_REVIEW_TOKEN = ""
            backend.MAPPING_REVIEWER_ID = ""

    def test_token_never_in_catalog_or_report_responses(self):
        backend.MAPPING_REVIEW_TOKEN = "secret-token"
        try:
            for url in ("/api/health", "/api/reports", "/api/reports/R1",
                        "/api/reports/R1/summary"):
                self.assertNotIn(b"secret-token",
                                 self.client.get(url).data, url)
        finally:
            backend.MAPPING_REVIEW_TOKEN = ""


class NonPositiveFactorValues(Base):
    """A stored status of "present" must not make 0 or a negative usable."""

    def put_factor(self, factor_id, value):
        DB.put(("factor_datasets", DATASET_ID, "factors", factor_id),
               factor_doc(factor_id, factor_value=value,
                          factor_status="present"))

    def test_zero_and_negative_present_factors_rejected_by_calculation(self):
        for fid, value in (("PRESENT_ZERO", 0), ("PRESENT_ZERO_F", 0.0),
                           ("PRESENT_NEG", -2.02633)):
            with self.subTest(factor=fid):
                self.put_factor(fid, value)
                res = self.calc(factor_id=fid)
                self.assertEqual(res.status_code, 422, res.get_json())
                self.assertEqual(res.get_json()["error_code"],
                                 "NO_APPLICABLE_FACTOR")
        self.assertEqual(self.entries(), [])
        self.assertEqual(DB.docs[("reports", "R1")]["totals"]["scope_1"], 0.0)

    def test_non_numeric_present_factor_rejected(self):
        for fid, value in (("PRESENT_STR", "2.0"), ("PRESENT_BOOL", True),
                           ("PRESENT_NAN", float("nan")),
                           ("PRESENT_INF", float("inf")),
                           ("PRESENT_NONE", None)):
            with self.subTest(factor=fid):
                self.put_factor(fid, value)
                self.assertEqual(self.calc(factor_id=fid).status_code, 422)

    def test_consistent_with_candidate_discovery(self):
        self.put_factor("PRESENT_ZERO", 0)
        self.put_factor("PRESENT_NEG", -1.5)
        listed = [f["factor_id"] for f in
                  self.client.get("/api/factors",
                                  query_string={"report_id": "R1"}
                                  ).get_json()["factors"]]
        for fid in ("PRESENT_ZERO", "PRESENT_NEG"):
            self.assertNotIn(fid, listed)
            self.assertEqual(self.calc(factor_id=fid).status_code, 422)
        # Every listed candidate with a matching unit is accepted by the
        # engine, so discovery never offers something calculation refuses.
        for fid in listed:
            if fid == "GAS_M3":
                self.assertEqual(self.calc(factor_id=fid).status_code, 200)


class AvailabilityWording(Base):
    """Dataset availability, candidates and calculation stay distinct."""

    def seed_approved_mapping(self):
        DB.put(("activity_factor_mappings", "M1"), {
            "mapping_id": "M1", "status": "approved",
            "dataset_id": DATASET_ID, "factor_id": "GAS_M3",
            "source_id": "defra_desnz", "dataset_year": 2026,
            "source_release": RELEASE,
            "industry_id": "steel_manufacturing", "process_id": "melting",
            "activity_id": "natural_gas_consumption",
            "activity_unit": "cubic metres", "scope_number": 1,
        })

    def activities(self, body):
        return [a for i in body["industries"] for p in i["processes"]
                for a in p["activities"]]

    def test_import_alone_does_not_mark_any_activity_available(self):
        body = self.client.get("/api/industries").get_json()
        acts = self.activities(body)
        self.assertTrue(acts)
        for a in acts:
            self.assertFalse(a["curated_suggestions_available"])
            self.assertFalse(a["factor_data_available"])
            self.assertTrue(a["factor_selection_required"])
            self.assertEqual(a["calculation_mode"],
                             "explicit_factor_selection")
            self.assertNotIn("calculation_available", a)

    def test_top_level_availability_explains_the_three_meanings(self):
        av = self.client.get("/api/industries").get_json()["availability"]
        self.assertTrue(av["dataset_available"])
        self.assertEqual(av["factor_candidates"]["endpoint"], "/api/factors")
        self.assertFalse(av["factor_candidates"]["applicability_assumed"])
        calc = av["calculation"]
        self.assertEqual(calc["mode"], "explicit_factor_selection")
        self.assertIn("factor_id", calc["requires"])
        self.assertFalse(calc["industry_process_mapping_required"])

    def test_dataset_status_does_not_claim_calculation_ready(self):
        ds = self.client.get("/api/datasets").get_json()["datasets"]
        self.assertTrue(ds["dataset_available"])
        self.assertFalse(ds["calculation_ready"])
        self.assertEqual(ds["calculation_readiness_status"],
                         "determined_per_report_and_selected_factor")
        self.assertEqual(ds["availability"]["calculation"]["mode"],
                         "explicit_factor_selection")

    def test_no_dataset_reports_unavailable(self):
        DB.docs.pop(("factor_datasets", DATASET_ID))
        av = self.client.get("/api/industries").get_json()["availability"]
        self.assertFalse(av["dataset_available"])
        ds = self.client.get("/api/datasets").get_json()["datasets"]
        self.assertFalse(ds["dataset_available"])
        self.assertEqual(ds["calculation_readiness_status"],
                         "no_imported_factor_dataset")

    def test_catalog_endpoint_carries_same_status(self):
        body = self.client.get("/api/catalog").get_json()
        self.assertFalse(body["datasets"]["calculation_ready"])
        self.assertIn("availability", body["datasets"])

    def test_curated_suggestion_is_optional_and_not_a_gate(self):
        self.seed_approved_mapping()
        acts = {(i["id"], p["id"], a["id"]): a
                for i in self.client.get("/api/industries")
                .get_json()["industries"]
                for p in i["processes"] for a in p["activities"]}
        suggested = acts[("steel_manufacturing", "melting",
                          "natural_gas_consumption")]
        self.assertTrue(suggested["curated_suggestions_available"])
        self.assertEqual(suggested["supported_factors"][0]["factor_id"],
                         "GAS_M3")
        self.assertTrue(suggested["factor_selection_required"])
        # An activity with no suggestion calculates just as well.
        other = acts[("steel_manufacturing", "casting",
                      "natural_gas_consumption")]
        self.assertFalse(other["curated_suggestions_available"])
        self.assertEqual(
            self.calc(process_id="casting").status_code, 200)

    def test_create_report_says_selection_is_still_required(self):
        res = self.client.post("/api/reports", json={
            "report_name": "R", "industry_id": "Anything",
            "reporting_year": 2026, "factor_source_id": "defra_desnz",
            "factor_dataset_year": 2026, "geography": "UK",
            "gwp_basis": "source_defined",
            "accounting_framework": "ghg_protocol_corporate",
            "report_id": "AVAIL1"})
        body = res.get_json()
        self.assertTrue(body["dataset_available"])
        self.assertTrue(body["factor_selection_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
