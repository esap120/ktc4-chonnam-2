from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from daesingo.evidence import (
    ContractInputError,
    PackageNotReady,
    aggregate_outcomes,
    assemble_evidence,
    build_report_package,
    correction_heads,
    evaluate_requirements,
    render_report,
    resolve_time,
    validate_contract,
)
from daesingo.evidence.mock_integration import run_scenario
from daesingo.evidence.policy import EVENT_POLICY, SPECIFIC_TEMPLATE_REF

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = json.loads((ROOT / "tests/evidence/fixtures/adapter_inputs.json").read_text(encoding="utf-8"))["scenarios"]


class ContractUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.happy = run_scenario(ROOT, "scenario_happy_001", CONFIGS["scenario_happy_001"])
        cls.record = cls.happy["outputs"]["evidence_records"][0]
        cls.time = cls.happy["outputs"]["time_resolutions"][0]
        cls.assets = json.loads((ROOT / "data/mock/recording/scenario_happy_001.json").read_text(encoding="utf-8"))["asset_facts"]

    def _ready_report(self):
        report = deepcopy(self.happy["outputs"]["requirement_reports"][1])
        report["overall"] = "PASS"
        return report

    def test_time_without_basis_is_unknown_and_has_no_resolved_value(self):
        result = resolve_time(
            time_source_candidates=[],
            overlay_time_readout=None,
            candidate_event={"span": {"representative_ms": 0}},
            case_id="case_unit",
            selection_rev=1,
            resolution_id="time_unit_unknown",
        )
        self.assertEqual("UNKNOWN", result["status"])
        self.assertNotIn("resolved", result)
        self.assertNotIn("selected_input_ref", result["provenance"])

    def test_outcome_precedence(self):
        def checks(values):
            return [{"outcome": value} for value in values]

        self.assertEqual("PASS", aggregate_outcomes(checks(["PASS", "PASS"])))
        self.assertEqual("WARN", aggregate_outcomes(checks(["PASS", "WARN"])))
        self.assertEqual("UNKNOWN", aggregate_outcomes(checks(["BLOCK", "UNKNOWN", "WARN", "PASS"])[1:]))
        self.assertEqual("BLOCK", aggregate_outcomes(checks(["UNKNOWN", "BLOCK", "WARN"])))

    def test_unknown_and_block_reports_do_not_build_packages(self):
        for overall in ("UNKNOWN", "BLOCK"):
            report = deepcopy(self.happy["outputs"]["requirement_reports"][1])
            report["overall"] = overall
            with self.assertRaisesRegex(PackageNotReady, "package.requirement_not_ready"):
                build_report_package(self.record, report, package_id=f"pkg_{overall}", created_at="2026-09-13T10:00:00+09:00", asset_facts=self.assets)

    def test_missing_and_unavailable_asset_produce_unknown_and_block(self):
        missing = evaluate_requirements(
            self.record, scope="FINAL_PACKAGE", report_id="req_missing",
            evaluated_at="2026-09-13T10:00:00+09:00",
            time_resolution=self.time, asset_facts=[],
        )
        unavailable_assets = deepcopy(self.assets)
        report_video = next(item for item in unavailable_assets if item.get("derived_role") == "REPORT_VIDEO")
        report_video["availability"] = "UNAVAILABLE"
        blocked = evaluate_requirements(
            self.record, scope="FINAL_PACKAGE", report_id="req_blocked",
            evaluated_at="2026-09-13T10:00:00+09:00",
            time_resolution=self.time, asset_facts=unavailable_assets,
        )
        def by_code(report):
            return {item["code"]: item for item in report["checks"]}
        self.assertEqual("UNKNOWN", by_code(missing)["package.asset.report_video.exists"]["outcome"])
        self.assertEqual("BLOCK", blocked["overall"])
        report_video["availability"] = "UNKNOWN"
        unknown = evaluate_requirements(
            self.record, scope="FINAL_PACKAGE", report_id="req_unknown_asset",
            evaluated_at="2026-09-13T10:00:00+09:00",
            time_resolution=self.time, asset_facts=unavailable_assets,
        )
        self.assertEqual("UNKNOWN", by_code(unknown)["package.asset.report_video.exists"]["outcome"])

    def test_missing_asset_and_failed_assembly_do_not_build_packages(self):
        report = self._ready_report()
        with self.assertRaisesRegex(PackageNotReady, "package.asset.report_video_missing"):
            build_report_package(self.record, report, package_id="pkg_no_asset", created_at="2026-09-13T10:00:00+09:00", asset_facts=[])
        with self.assertRaisesRegex(PackageNotReady, "package.assembly_failed"):
            build_report_package(self.record, report, package_id="pkg_failed", created_at="2026-09-13T10:00:00+09:00", asset_facts=self.assets, assembly_succeeded=False)

    def test_plate_image_is_optional_and_package_supersede_is_additive(self):
        report = self._ready_report()
        report_only = [item for item in self.assets if item.get("derived_role") == "REPORT_VIDEO"]
        package = build_report_package(self.record, report, package_id="pkg_unit", created_at="2026-09-13T10:00:00+09:00", asset_facts=report_only)
        self.assertNotIn("plate_image_ref", package["assets"])
        replacement = build_report_package(self.record, report, package_id="pkg_unit_v2", created_at="2026-09-13T10:01:00+09:00", asset_facts=report_only, supersedes_id="pkg_unit")
        self.assertEqual({"kind": "report_package", "ref": "pkg_unit"}, replacement["supersedes_ref"])
        self.assertEqual("pkg_unit", package["package_ref"]["ref"])

    def test_active_catalog_applies_adopted_size_and_deadline_rules(self):
        report = self.happy["outputs"]["requirement_reports"][1]
        codes = {item["code"] for item in report["checks"]}
        self.assertIn("package.asset.video.each_size", codes)
        self.assertIn("package.deadline.within_policy", codes)
        self.assertNotIn("package.asset.report_video.size", codes)
        # #280 — ADR-EVIDENCE-010이 활성 catalog를 v6로 바꿨다.
        self.assertEqual("policy/requirement-rules-v6", report["policy_ref"])

    def test_all_four_event_mappings_render_with_adopted_template_and_length(self):
        for visual_type, policy in EVENT_POLICY.items():
            rendered = render_report(
                visual_event_type=visual_type,
                situation_response="CONFIRMED",
                occurred_at="2026-09-13T10:00:00+09:00",
                location_display="서울시 테스트로 1",
                vehicle_number="12가3456",
                violation_expression=policy["violation_expression"],
            )
            self.assertEqual(SPECIFIC_TEMPLATE_REF, rendered["template_ref"])
            self.assertGreaterEqual(rendered["content_length"], 5)
            self.assertLessEqual(rendered["content_length"], 900)
        generic = render_report(
            visual_event_type=None,
            situation_response="USER_UNSURE",
            occurred_at="2026-09-13T10:00:00+09:00",
            location_display="서울시 테스트로 1",
            vehicle_number="12가3456",
            violation_expression="확인이 필요한 주행 상황",
        )
        self.assertEqual("tmpl/safety-report-generic-v1", generic["template_ref"])
        self.assertGreaterEqual(generic["content_length"], 5)
        self.assertLessEqual(generic["content_length"], 900)

    def test_renderer_rejects_specific_report_without_user_confirmation(self):
        with self.assertRaisesRegex(ContractInputError, "report.input.situation_unconfirmed"):
            render_report(
                visual_event_type="SIGNAL",
                situation_response=None,
                occurred_at="2026-09-13T10:00:00+09:00",
                location_display="서울시 테스트로 1",
                vehicle_number="12가3456",
                violation_expression=EVENT_POLICY["SIGNAL"]["violation_expression"],
            )

    def test_renderer_rejects_generic_report_without_user_unsure_response(self):
        with self.assertRaisesRegex(ContractInputError, "report.input.user_unsure_required"):
            render_report(
                visual_event_type=None,
                situation_response=None,
                occurred_at="2026-09-13T10:00:00+09:00",
                location_display="서울시 테스트로 1",
                vehicle_number="12가3456",
                violation_expression="확인이 필요한 주행 상황",
            )

    def test_unconfirmed_specific_evidence_cannot_build_package(self):
        unconfirmed = deepcopy(self.record)
        unconfirmed.pop("situation_response")
        report = self._ready_report()
        with self.assertRaisesRegex(PackageNotReady, "package.input.situation_unconfirmed"):
            build_report_package(
                unconfirmed,
                report,
                package_id="pkg_unconfirmed",
                created_at="2026-09-13T10:00:00+09:00",
                asset_facts=self.assets,
            )

    def test_correction_head_validates_type_chain_and_actual_application(self):
        first = self._correction("corr_plate_1", "vehicle_number", "11가1111", "22나2222", kind="PLATE_MANUAL_EDIT")
        second = self._correction("corr_plate_2", "vehicle_number", "22나2222", "33다3333", kind="PLATE_MANUAL_EDIT", supersedes="corr_plate_1")
        heads = correction_heads([first, second], case_id="case_h001", selection_rev=1)
        self.assertEqual("corr_plate_2", heads["vehicle_number"]["correction_id"])
        assembled = self._reassemble([first, second])
        self.assertEqual("33다3333", assembled["vehicle_number"]["value"])
        self.assertTrue(assembled["vehicle_number"]["user_corrected"])
        self.assertIn({"kind": "correction_record", "ref": "corr_plate_2"}, assembled["provenance"]["correction_refs"])
        with self.assertRaises(ContractInputError):
            correction_heads([self._correction("bad", "location.coord", {"lat": 1, "lon": 2}, "not-a-coordinate")], case_id="case_h001", selection_rev=1)

    def test_all_ten_evidence_correction_target_types(self):
        values = {
            "event.visual_event_type": ("SIGNAL", "CENTER_LINE_CROSSING"),
            "event.safety_report_type": ("TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION"),
            "event.violation_expression": ("기존 위반 표현", "수정된 위반 표현"),
            "occurred_at": ("2026-09-13T10:00:00+09:00", "2026-09-13T10:01:00+09:00"),
            "vehicle_number": ("11가1111", "22나2222"),
            "location.coord": ({"lat": 35.1, "lon": 126.1}, {"lat": 35.2, "lon": 126.2}),
            "location.address": ("이전 주소", "수정 주소"),
            "location.place_name": ("이전 장소", "수정 장소"),
            "location.search_keyword": ("이전 검색어", "수정 검색어"),
            "location.user_hint": ("이전 위치 단서", "수정 위치 단서"),
        }
        kinds = {
            "event.visual_event_type": "SITUATION_CHANGE",
            "occurred_at": "EVENT_TIME_MANUAL",
            "vehicle_number": "PLATE_MANUAL_EDIT",
        }
        records = [
            self._correction(f"corr_type_{index}", target, previous, new, kind=kinds.get(target, "REPORT_TYPE_CHANGE"))
            for index, (target, (previous, new)) in enumerate(values.items())
        ]
        self.assertEqual(set(values), set(correction_heads(records, case_id="case_h001", selection_rev=1)))

    def test_nine_non_time_corrections_have_k4_value_provenance(self):
        values = {
            "event.visual_event_type": ("SIGNAL", "CENTER_LINE_CROSSING"),
            "event.safety_report_type": ("TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION"),
            "event.violation_expression": ("기존 위반 표현", "사용자가 직접 수정한 위반 표현"),
            "vehicle_number": ("11가1111", "22나2222"),
            "location.coord": ({"lat": 35.1, "lon": 126.1}, {"lat": 35.2, "lon": 126.2}),
            "location.address": ("이전 주소", "수정 주소"),
            "location.place_name": ("이전 장소", "수정 장소"),
            "location.search_keyword": ("이전 검색어", "수정 검색어"),
            "location.user_hint": ("이전 위치 단서", "수정 위치 단서"),
        }
        for index, (target, (previous, new)) in enumerate(values.items()):
            with self.subTest(target=target):
                kind = "SITUATION_CHANGE" if target == "event.visual_event_type" else "PLATE_MANUAL_EDIT" if target == "vehicle_number" else "REPORT_TYPE_CHANGE"
                correction = self._correction(f"corr_k4_{index}", target, previous, new, kind=kind)
                situation = None
                if target == "event.visual_event_type":
                    situation = {"value": "CORRECTED", "responded_at": "2026-09-13T10:00:00+09:00",
                                 "candidate_ref": {"kind": "candidate_event", "ref": "candidate_h001"}}
                assembled = self._reassemble([correction], situation_response=situation)
                if target.startswith("event."):
                    value = assembled["event"][target.split(".", 1)[1]]
                elif target.startswith("location."):
                    value = assembled["location"][target.split(".", 1)[1]]
                else:
                    value = assembled[target]
                ref = {"kind": "correction_record", "ref": correction["correction_id"]}
                self.assertEqual(new, value["value"])
                self.assertEqual({"kind": "case.user_correction", "ref": ref,
                                  "observability": "OBSERVED", "label_key": None}, value["source"])
                self.assertEqual([ref], value["support_refs"])
                self.assertTrue(value["user_corrected"])
                self.assertFalse(value["needs_review"])
                self.assertIn(ref, assembled["provenance"]["correction_refs"])
                self.assertEqual([], validate_contract(assembled))

    def test_visual_correction_keeps_derived_mapping_inferred_until_direct_override(self):
        visual = self._correction("corr_visual_map", "event.visual_event_type", "SIGNAL",
                                  "CENTER_LINE_CROSSING", kind="SITUATION_CHANGE")
        situation = {"value": "CORRECTED", "responded_at": "2026-09-13T10:00:00+09:00",
                     "candidate_ref": {"kind": "candidate_event", "ref": "candidate_h001"}}
        assembled = self._reassemble([visual], situation_response=situation)
        report_type = assembled["event"]["safety_report_type"]
        expression = assembled["event"]["violation_expression"]
        self.assertEqual(("evidence.category_mapping", "INFERRED", False), (
            report_type["source"]["kind"], report_type["source"]["observability"],
            report_type["user_corrected"]))
        self.assertEqual(("evidence.violation_expression", "INFERRED", False), (
            expression["source"]["kind"], expression["source"]["observability"],
            expression["user_corrected"]))

        direct = self._correction("corr_report_type", "event.safety_report_type",
                                  "TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION")
        overridden = self._reassemble([visual, direct], situation_response=situation)
        direct_value = overridden["event"]["safety_report_type"]
        self.assertEqual("case.user_correction", direct_value["source"]["kind"])
        self.assertEqual("OBSERVED", direct_value["source"]["observability"])
        self.assertTrue(direct_value["user_corrected"])

    def test_occurred_at_correction_does_not_gain_evidence_value_source_fields(self):
        result = run_scenario(ROOT, "scenario_correction_rerun_001", CONFIGS["scenario_correction_rerun_001"])
        occurred = result["outputs"]["evidence_records"][-1]["occurred_at"]
        self.assertNotIn("observability", occurred["source"])
        self.assertNotIn("ref", occurred["source"])
        self.assertEqual("time.source.user_correction", occurred["source"]["label_key"])

    def test_corrected_situation_requires_change_but_user_unsure_does_not(self):
        situation = {"value": "CORRECTED", "responded_at": "2026-09-13T10:00:00+09:00", "candidate_ref": {"kind": "candidate_event", "ref": "candidate_h001"}}
        with self.assertRaisesRegex(ContractInputError, "SITUATION_CHANGE"):
            self._reassemble([], situation_response=situation)
        change = self._correction("corr_situation", "event.visual_event_type", "SIGNAL", "CENTER_LINE_CROSSING", kind="SITUATION_CHANGE")
        assembled = self._reassemble([change], situation_response=situation)
        self.assertEqual("CORRECTED", assembled["situation_response"]["value"])
        self.assertEqual("CENTER_LINE_CROSSING", assembled["event"]["visual_event_type"]["value"])
        unsure = {"value": "USER_UNSURE", "responded_at": "2026-09-13T10:00:00+09:00", "candidate_ref": None}
        self.assertEqual("USER_UNSURE", self._reassemble([], situation_response=unsure)["situation_response"]["value"])

    def _correction(self, correction_id, target, previous, new, *, kind="REPORT_TYPE_CHANGE", supersedes=None):
        return {
            "contract_version": "correction-record/v1.1",
            "correction_id": correction_id,
            "case_id": "case_h001",
            "selection_rev": 1,
            "kind": kind,
            "target_field": target,
            "previous_value": previous,
            "new_value": new,
            "supersedes_ref": None if supersedes is None else {"kind": "correction_record", "ref": supersedes},
            "corrected_at": "2026-09-13T10:00:00+09:00",
        }

    def _reassemble(self, corrections, situation_response=None):
        recording = json.loads((ROOT / "data/mock/recording/scenario_happy_001.json").read_text(encoding="utf-8"))
        search = json.loads((ROOT / "data/mock/search/scenario_happy_001.json").read_text(encoding="utf-8"))
        readout = json.loads((ROOT / "data/mock/readout/scenario_happy_001.json").read_text(encoding="utf-8"))
        case = json.loads((ROOT / "data/mock/case/scenario_happy_001.json").read_text(encoding="utf-8"))
        candidate = next(item for group in search["analysis_run_candidate_events"] for item in group["candidates"] if item["candidate_id"] == "candidate_h001")
        visual = next(item for item in search["visual_evidences"] if item["candidate_id"] == "candidate_h001")
        time = self.happy["outputs"]["time_resolutions"][0]
        return assemble_evidence(
            case_id="case_h001", selection_rev=1, candidate_event=candidate, visual_evidence=visual,
            time_resolution=time, plate_readout=readout["plate_readouts"][0], incident_clip=recording["incident_clips"][0],
            record_id="ev_correction_unit", location_hint=case["case_views"][-1]["hints"]["location"],
            correction_records=corrections, situation_response=situation_response,
        )


if __name__ == "__main__":
    unittest.main()
