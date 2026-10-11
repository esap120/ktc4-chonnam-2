"""#146 · #172 D · D-2 · D-3 — 번호판 식별 실패와 실행 실패의 경계(ADR-EVIDENCE-008).

- WARN = 판독·관찰을 실제로 수행했고 번호판 정보가 부족함을 확인한 경우 → 번호판 없이도 Package
- UNKNOWN = 아직 판정할 수 없거나 판독 결과 자체가 없는 경우
- 실행 실패(PlateReadout=None)는 WARN으로 위장하지 않는다 — Package가 없고 READY로 가지 않는다

기록은 모두 실제 `assemble_evidence()`로 만든다. 입력 PlateReadout만 상황별로 바꾸고,
Package는 실제 `build_report_package()`로, READY는 case의 `mark_ready_if_package_ready()`로 확인한다.

#280(ADR-EVIDENCE-010) 이후 최종 REPORT_VIDEO 관찰(I4)은 MVP FINAL rule이 아니다. 관찰 입력은
기본으로 비어 있고(real 경로의 `observation_facts=None`과 같다), 그래도 아래 경계는 그대로다.
"""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

from daesingo.case import service as case_service
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.evidence import (
    ContractInputError,
    PackageNotReady,
    build_report_package,
    calculate_evidence_needs,
    evaluate_requirements,
    render_report,
    validate_contract,
)
from daesingo.evidence import mock_integration as mock
from daesingo.evidence.disposition import ASSEMBLE
from daesingo.evidence.policy_catalog import load_requirement_catalog

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = json.loads((ROOT / "tests/evidence/fixtures/adapter_inputs.json").read_text(encoding="utf-8"))["scenarios"]
SCENARIO = "scenario_happy_001"
EVIDENCE_AT, FINAL_AT = CONFIGS[SCENARIO]["evaluated_at"]
CREATED_AT = CONFIGS[SCENARIO]["package_created_at"]


class _Snapshot:
    """case `fetch_case_view_inputs()`가 읽는 getter만 가진 evidence 결과 스냅샷.

    record는 항상 조립된 뒤이므로 Fine 소비 판정은 `ASSEMBLE`이고, needs는 같은 record·PlateReadout으로
    evidence가 계산한 값이다(real adapter의 `get_visual_evidence_decision`·`get_evidence_needs`와 같은 의미).
    """

    def __init__(self, record: dict[str, Any], final: dict[str, Any], package: dict[str, Any] | None,
                 needs: dict[str, Any]):
        self._record, self._final, self._package, self._needs = record, final, package, needs

    def get_evidence_record(self):
        return self._record

    def get_evidence_needs(self):
        return [self._needs]

    def get_visual_evidence_decision(self):
        return ASSEMBLE

    def get_independent_facts(self):
        return None

    def get_requirement_report(self, scope):
        return self._final if scope == "FINAL_PACKAGE" else None

    def get_report_package(self):
        return self._package

    def get_plate_read_status(self):
        return None

    def get_plate_readouts(self):
        return []

    def get_overlay_time_readouts(self):
        return []


class PlateBoundaryD3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = CONFIGS[SCENARIO]
        cls.happy = mock.run_scenario(ROOT, SCENARIO, cls.config)
        cls.time = cls.happy["outputs"]["time_resolutions"][0]
        cls.upstream = mock._upstream(ROOT, SCENARIO)
        cls.plate = cls.upstream["readout"]["plate_readouts"][0]
        cls.assets = json.loads(
            (ROOT / "data/mock/recording/scenario_happy_001.json").read_text(encoding="utf-8"))["asset_facts"]

    # --- inputs -------------------------------------------------------------------------------

    def _record(self, plate):
        return mock._assemble(upstream=self.upstream, config=self.config, time=self.time,
                              plate=plate, record_id="ev_d3_unit")

    def _unread_plate(self):
        plate = deepcopy(self.plate)
        plate["observation"]["value"] = None
        plate["observation"]["status"] = "UNKNOWN"
        return plate

    def _partial_plate(self):
        plate = deepcopy(self.plate)
        plate["observation"]["value"] = "12가34?6"
        plate["observation"]["status"] = "NEEDS_REVIEW"
        plate["abstained"] = True
        return plate

    @staticmethod
    def _legacy_i4_facts(plate_visible):
        """v5까지 I4가 넘기려던 최종 영상 관찰. v6는 이 key를 읽는 rule이 없다."""
        return {
            "plate_visible_in_report_video": {
                "value": plate_visible,
                "subject_refs": [{"kind": "derived_asset", "ref": "da_h001_report_video"}]},
            "time_overlay_visible": {
                "value": plate_visible,
                "subject_refs": [{"kind": "derived_asset", "ref": "da_h001_report_video"}]},
        }

    # --- pipeline -----------------------------------------------------------------------------

    def _run(self, plate, *, observation_facts=None):
        """EVIDENCE → FINAL → Package(없으면 None) → case READY 여부."""
        record = self._record(plate)
        evidence = evaluate_requirements(record, scope="EVIDENCE", report_id="req_d3_evidence",
                                         evaluated_at=EVIDENCE_AT, time_resolution=self.time)
        final = evaluate_requirements(record, scope="FINAL_PACKAGE", report_id="req_d3_final",
                                      evaluated_at=FINAL_AT, time_resolution=self.time,
                                      asset_facts=self.assets, observation_facts=observation_facts)
        try:
            package = build_report_package(record, final, package_id="pkg_d3_unit",
                                           created_at=CREATED_AT, asset_facts=self.assets)
        except PackageNotReady:
            package = None
        # case는 현재 선택 context(candidate_ref·selection_rev)의 record일 때만 READY로 올린다(#191).
        candidate_id = record["basis"]["candidate_ref"]["ref"]
        case = CaseAggregate.intake(case_id="case_d3", hints={}, manifest_summary={})
        case.start_search()
        case.receive_candidates([Candidate(candidate_id=candidate_id, at=None, at_provenance=None,
                                           observed="", thumb_ref=None, rank=1)])
        case.select_candidate(candidate_id)
        ready = case_service.mark_ready_if_package_ready(case, _Snapshot(record, final, package, calculate_evidence_needs(record, plate)))
        return record, evidence, final, package, ready, case.stage

    @staticmethod
    def _check(report, code):
        return next(item for item in report["checks"] if item["code"] == code)

    # --- catalog ------------------------------------------------------------------------------

    def test_active_catalog_is_v6_superseding_v5(self):
        catalog = load_requirement_catalog()
        self.assertEqual("policy/requirement-rules-v6", catalog["policy_ref"])
        self.assertEqual("policy/requirement-rules-v5", catalog["supersedes_policy_ref"])
        self.assertEqual("safety-report-policy/v1.2", catalog["referenced_policies"]["report_template"])

    def test_v5_revision_is_preserved_with_its_i4_rules(self):
        v5 = json.loads((ROOT / "src/daesingo/evidence/requirement_rules_v5.json").read_text(encoding="utf-8"))
        rule = next(item for item in v5["scopes"]["FINAL_PACKAGE"]["always"]
                    if item["code"] == "package.vehicle.plate_visible_in_report_video")
        self.assertEqual("policy/requirement-rules-v5", v5["policy_ref"])
        self.assertEqual(("WARN", "UNKNOWN"), (rule["outcomes"]["observed_false"], rule["outcomes"]["not_observed"]))

    def test_v4_revision_is_preserved_with_its_historical_block(self):
        v4 = json.loads((ROOT / "src/daesingo/evidence/requirement_rules_v4.json").read_text(encoding="utf-8"))
        rule = next(item for item in v4["scopes"]["FINAL_PACKAGE"]["always"]
                    if item["code"] == "package.vehicle.plate_visible_in_report_video")
        self.assertEqual("policy/requirement-rules-v4", v4["policy_ref"])
        self.assertEqual("BLOCK", rule["outcomes"]["observed_false"])

    # --- 1 · 번호판 정상 ----------------------------------------------------------------------

    def test_1_plate_secured_pass_and_package(self):
        _, evidence, final, package, ready, stage = self._run(self.plate)
        check = self._check(evidence, "evidence.vehicle_number.present")
        self.assertEqual(("PASS", "evidence.value_confirmed"), (check["outcome"], check["reason_code"]))
        self.assertEqual("PASS", final["overall"])
        self.assertEqual([], validate_contract(package))
        self.assertEqual("12가3456", package["report_inputs"]["vehicle_number"])
        self.assertEqual("tmpl/safety-report-specific-v1", package["report"]["template_ref"])
        self.assertTrue(ready)
        self.assertEqual("READY", stage)

    # --- 2 · 판독 성공 + 식별 실패 -------------------------------------------------------------

    def test_2_readout_ran_but_read_nothing_is_warn_and_still_builds_a_package(self):
        record, evidence, final, package, ready, stage = self._run(self._unread_plate())
        self.assertNotIn("vehicle_number", record)  # 값을 만들지 않는다 — sentinel 없음
        check = self._check(evidence, "evidence.vehicle_number.present")
        self.assertEqual(("WARN", "evidence.plate_unidentified"), (check["outcome"], check["reason_code"]))
        self.assertEqual("WARN", evidence["overall"])
        # 1·3은 재판독 대상이 아니다(abstained=false).
        self.assertEqual([], calculate_evidence_needs(record, self._unread_plate())["items"])
        # 번호판 부족 자체로 FINAL이 BLOCK/UNKNOWN이 되지 않는다.
        self.assertIn(final["overall"], {"PASS", "WARN"})
        self.assertEqual("PASS", self._check(final, "package.report.content_length")["outcome"])
        self.assertEqual([], validate_contract(package))
        self.assertEqual("report-package/v1.2", package["contract_version"])
        self.assertIsNone(package["report_inputs"]["vehicle_number"])
        self.assertEqual("tmpl/safety-report-specific-no-plate-v1", package["report"]["template_ref"])
        self.assertTrue(ready)
        self.assertEqual("READY", stage)

    # --- 3 · 일부 판독 / NEEDS_REVIEW ----------------------------------------------------------

    def test_3_partial_read_is_warn_keeps_reread_need_and_is_not_a_package_blocker(self):
        plate = self._partial_plate()
        record, evidence, final, package, ready, _ = self._run(plate)
        self.assertNotIn("vehicle_number", record)  # 「12가34?6」은 확정값으로 승격하지 않는다
        self.assertEqual("WARN", self._check(evidence, "evidence.vehicle_number.present")["outcome"])
        self.assertEqual(["PLATE_REREAD"], [item["kind"] for item in calculate_evidence_needs(record, plate)["items"]])
        self.assertIn(final["overall"], {"PASS", "WARN"})
        self.assertIsNotNone(package)
        self.assertIsNone(package["report_inputs"]["vehicle_number"])
        self.assertNotIn("34?6", package["report"]["description"])
        self.assertTrue(ready)

    # --- I4 (#280 · ADR-EVIDENCE-010) -----------------------------------------------------------

    def test_4_no_report_video_observation_is_not_a_final_gate(self):
        # v5까지는 I4 미관찰 → UNKNOWN → Package 없음이었다. v6는 이 rule이 없다.
        for observation_facts in (None, {}):
            with self.subTest(observation_facts=observation_facts):
                _, _, final, package, ready, stage = self._run(self.plate, observation_facts=observation_facts)
                self.assertNotIn("package.vehicle.plate_visible_in_report_video",
                                 [item["code"] for item in final["checks"]])
                self.assertEqual("PASS", final["overall"])
                self.assertEqual([], validate_contract(package))
                self.assertTrue(ready)
                self.assertEqual("READY", stage)

    def test_5_legacy_i4_observation_is_ignored_even_when_not_visible(self):
        # 관찰값이 들어와도 판정하지 않는다 — 「보인다」고도 「안 보인다」고도 말하지 않는다.
        _, _, baseline, _, _, _ = self._run(self.plate)
        for visible in (True, False):
            with self.subTest(visible=visible):
                _, _, final, package, ready, _ = self._run(
                    self.plate, observation_facts=self._legacy_i4_facts(visible))
                self.assertEqual(baseline["checks"], final["checks"])
                self.assertEqual("PASS", final["overall"])
                self.assertIsNotNone(package)
                self.assertTrue(ready)

    # --- 4a · 실행 실패 ------------------------------------------------------------------------

    def test_6_readout_execution_failure_is_unknown_no_package_no_ready(self):
        # 4a: ReadoutRun.outcome=FAILED면 PlateReadout=None이 온다. 식별 실패 WARN으로 바꾸지 않는다.
        # 최종 영상 관찰이 「보인다」로 들어와도 결과는 같아야 한다 — 실행 실패는 렌더 입력에서 막힌다.
        record, evidence, final, package, ready, stage = self._run(
            None, observation_facts=self._legacy_i4_facts(True))
        self.assertFalse(any(ref["kind"] == "plate_readout" for ref in record["provenance"]["input_refs"]))
        check = self._check(evidence, "evidence.vehicle_number.present")
        self.assertEqual(("UNKNOWN", "evidence.plate_readout_missing"), (check["outcome"], check["reason_code"]))
        self.assertEqual("UNKNOWN", evidence["overall"])
        self.assertEqual("UNKNOWN", self._check(final, "package.report.content_length")["outcome"])
        self.assertNotIn(final["overall"], {"PASS", "WARN"})
        self.assertIsNone(package)
        self.assertFalse(ready)
        self.assertEqual("EVIDENCE_REVIEW", stage)
        # blocking notice(readout.plate_read_failed)는 case가 투영한다:
        # tests/case/test_plate_read_failure_projection.py

    def test_6b_builder_refuses_a_plate_less_record_without_plate_readout_even_if_report_says_warn(self):
        # FINAL이 어떤 경로로든 PASS/WARN이어도 builder가 실행 실패 기록을 Package로 만들지 않는다.
        record = self._record(None)
        ready_report = evaluate_requirements(
            self._record(self.plate), scope="FINAL_PACKAGE", report_id="req_d3_forged",
            evaluated_at=FINAL_AT, time_resolution=self.time, asset_facts=self.assets)
        ready_report["basis"]["evidence_record_ref"] = deepcopy(record["record_ref"])
        with self.assertRaisesRegex(PackageNotReady, "package.input.vehicle_number_missing"):
            build_report_package(record, ready_report, package_id="pkg_d3_forged",
                                 created_at=CREATED_AT, asset_facts=self.assets)

    # --- 번호판 없는 신고문 --------------------------------------------------------------------

    def test_7_no_plate_report_renders_without_sentinel_or_invented_plate(self):
        cases = (
            ("SOLID_LINE_LANE_CHANGE", "CONFIRMED", "미금역 사거리", "tmpl/safety-report-specific-no-plate-v1"),
            ("SOLID_LINE_LANE_CHANGE", "CONFIRMED", None, "tmpl/safety-report-specific-no-location-no-plate-v1"),
            (None, "USER_UNSURE", "미금역 사거리", "tmpl/safety-report-generic-no-plate-v1"),
            (None, "USER_UNSURE", None, "tmpl/safety-report-generic-no-location-no-plate-v1"),
        )
        for visual, response, location, template in cases:
            with self.subTest(template=template):
                rendered = render_report(
                    visual_event_type=visual, situation_response=response,
                    occurred_at="2026-08-24T18:31:48+09:00", location_display=location,
                    vehicle_number=None, violation_expression="백색 실선을 넘어 진로를 변경")
                text = rendered["description"]
                self.assertEqual(template, rendered["template_ref"])
                self.assertNotIn("UNKNOWN", text)
                self.assertNotIn("차량번호 ", text.replace("차량번호는", ""))  # 번호 슬롯이 없다
                self.assertTrue(text.endswith("차량번호는 영상에서 식별하지 못했습니다."))  # 부족을 숨기지 않는다

    def test_7b_plate_present_text_is_unchanged_from_v1_1(self):
        rendered = render_report(
            visual_event_type="SOLID_LINE_LANE_CHANGE", situation_response="CONFIRMED",
            occurred_at="2026-08-24T18:31:48+09:00", location_display="미금역 사거리",
            vehicle_number="12가3456", violation_expression="백색 실선을 넘어 진로를 변경")
        self.assertEqual(
            "2026-08-24 18:31:48경 미금역 사거리에서\n차량번호 12가3456 차량이\n"
            "백색 실선을 넘어 진로를 변경하는 것을 확인하여 신고합니다.\n"
            "첨부 영상에서 해당 위반 상황을 확인할 수 있습니다.",
            rendered["description"])

    def test_7c_renderer_rejects_blank_plate_instead_of_treating_it_as_absent(self):
        for blank in ("", "  "):
            with self.subTest(blank=blank), self.assertRaises(ContractInputError):
                render_report(visual_event_type="SIGNAL", situation_response="CONFIRMED",
                              occurred_at="2026-08-24T18:31:48+09:00", location_display=None,
                              vehicle_number=blank, violation_expression="적색신호 상태에서 정지하지 않고 진행")


if __name__ == "__main__":
    unittest.main()
