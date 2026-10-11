"""#280 — 최종 REPORT_VIDEO 재관찰(I4) rule을 MVP FINAL에서 뺀다(ADR-EVIDENCE-010).

`policy/requirement-rules-v6`는 `package.vehicle.plate_visible_in_report_video`와
`package.time.overlay_visible`을 선택하지 않는다. 확인하는 것은 두 가지다.

- I4 관찰이 없다는 사실 자체는 FINAL을 `UNKNOWN`으로 만들지 않는다.
- 다른 rule의 `UNKNOWN`/`BLOCK`은 그대로다 — 이 결정이 다른 gate를 느슨하게 하지 않는다.

번호판 식별 실패 경계(#172 D-3)의 회귀는 `test_plate_boundary_d3.py`가 맡는다.
"""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from daesingo.evidence import (
    PackageNotReady,
    build_report_package,
    evaluate_requirements,
    validate_contract,
)
from daesingo.evidence.mock_integration import run_scenario
from daesingo.evidence.policy_catalog import load_requirement_catalog

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = json.loads((ROOT / "tests/evidence/fixtures/adapter_inputs.json").read_text(encoding="utf-8"))["scenarios"]
SCENARIO = "scenario_happy_001"
FINAL_AT = CONFIGS[SCENARIO]["evaluated_at"][1]
CREATED_AT = CONFIGS[SCENARIO]["package_created_at"]
REMOVED_CODES = {"package.vehicle.plate_visible_in_report_video", "package.time.overlay_visible"}


class I4RulesRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        happy = run_scenario(ROOT, SCENARIO, CONFIGS[SCENARIO])
        cls.record = happy["outputs"]["evidence_records"][0]
        cls.time = happy["outputs"]["time_resolutions"][0]
        cls.assets = json.loads(
            (ROOT / "data/mock/recording/scenario_happy_001.json").read_text(encoding="utf-8"))["asset_facts"]

    def _final(self, *, record=None, time=None, assets=None, observation_facts=None):
        return evaluate_requirements(
            record or self.record, scope="FINAL_PACKAGE", report_id="req_i4_unit",
            evaluated_at=FINAL_AT, time_resolution=time or self.time,
            asset_facts=self.assets if assets is None else assets,
            observation_facts=observation_facts)

    def _package(self, report, *, record=None, assets=None):
        return build_report_package(record or self.record, report, package_id="pkg_i4_unit",
                                    created_at=CREATED_AT,
                                    asset_facts=self.assets if assets is None else assets)

    @staticmethod
    def _outcomes(report):
        return {item["code"]: item["outcome"] for item in report["checks"]}

    def _report_video(self, assets, **changes):
        assets = deepcopy(assets)
        video = next(item for item in assets if item.get("derived_role") == "REPORT_VIDEO")
        video.update(changes)
        return assets

    # --- 제거 ---------------------------------------------------------------------------------

    def test_active_catalog_selects_neither_visibility_rule(self):
        catalog = load_requirement_catalog()
        final = catalog["scopes"]["FINAL_PACKAGE"]
        codes = {item["code"] for item in final["always"]}
        codes |= {case["code"] for case in final["conditional"][0]["cases"] if "code" in case}
        self.assertTrue(REMOVED_CODES.isdisjoint(codes))
        self.assertEqual(11, len(final["always"]))
        self.assertEqual("policy/requirement-rules-v6", catalog["policy_ref"])

    # --- A · 번호판 가시성 관찰 없음 ------------------------------------------------------------

    def test_a_no_plate_visibility_observation_does_not_make_final_unknown(self):
        report = self._final(observation_facts=None)
        self.assertNotIn("package.vehicle.plate_visible_in_report_video", self._outcomes(report))
        self.assertEqual("PASS", report["overall"])
        self.assertEqual([], validate_contract(self._package(report)))

    # --- B · 시각 overlay 가시성 관찰 없음 ------------------------------------------------------

    def test_b_verified_overlay_branch_selects_no_time_rule_and_does_not_block(self):
        self.assertEqual(("OK", "time.verified_overlay_already_present"),
                         (self.time["status"], self.time["post_stamp"]["reason_code"]))
        report = self._final(observation_facts={})
        self.assertEqual([], [code for code in self._outcomes(report) if code.startswith("package.time.")])
        self.assertEqual("PASS", report["overall"])
        self.assertIsNotNone(self._package(report))

    def test_b_legacy_visibility_inputs_are_ignored(self):
        baseline = self._final(observation_facts={})
        legacy = {
            "plate_visible_in_report_video": {"value": False, "subject_refs": []},
            "time_overlay_visible": {"value": False, "subject_refs": []},
        }
        self.assertEqual(baseline["checks"], self._final(observation_facts=legacy)["checks"])
        # 구조가 깨진 legacy 값도 읽지 않는다 — 읽는 rule이 없다.
        malformed = {"plate_visible_in_report_video": {"value": "yes"}, "time_overlay_visible": "yes"}
        self.assertEqual(baseline["checks"], self._final(observation_facts=malformed)["checks"])

    # --- C · 다른 gate는 그대로 ----------------------------------------------------------------

    def test_c_missing_report_video_still_blocks_the_package(self):
        assets = [item for item in self.assets if item.get("derived_role") != "REPORT_VIDEO"]
        report = self._final(assets=assets)
        self.assertEqual("UNKNOWN", self._outcomes(report)["package.asset.report_video.exists"])
        self.assertEqual("UNKNOWN", report["overall"])
        with self.assertRaises(PackageNotReady):
            self._package(report, assets=assets)

    def test_c_unavailable_report_video_is_still_block(self):
        assets = self._report_video(self.assets, availability="UNAVAILABLE")
        report = self._final(assets=assets)
        self.assertEqual("BLOCK", self._outcomes(report)["package.asset.report_video.exists"])
        self.assertEqual("BLOCK", report["overall"])

    def test_c_unknown_report_video_size_is_still_unknown(self):
        assets = self._report_video(self.assets, byte_size=None)
        report = self._final(assets=assets)
        outcomes = self._outcomes(report)
        self.assertEqual("UNKNOWN", outcomes["package.asset.video.each_size"])
        self.assertEqual("UNKNOWN", outcomes["package.asset.total_size"])
        self.assertEqual("UNKNOWN", report["overall"])

    def test_c_unresolved_occurred_at_is_still_unknown(self):
        record, time = deepcopy(self.record), deepcopy(self.time)
        record.pop("occurred_at")
        time["status"] = "UNKNOWN"
        time["post_stamp"] = {"needed": False, "reason_code": "time.no_resolvable_source",
                              "requires_user_notice": False}
        report = self._final(record=record, time=time)
        outcomes = self._outcomes(report)
        self.assertEqual("UNKNOWN", outcomes["package.time.display_unresolved"])
        self.assertEqual("UNKNOWN", outcomes["package.deadline.within_policy"])
        self.assertEqual("UNKNOWN", report["overall"])

    def test_c_post_stamp_fact_is_not_part_of_i4_and_still_gates(self):
        # 사후 각인은 REPORT_VIDEO를 만드는 recording의 transform 사실이다(ADR-005 §5.5). I4가 아니다.
        time = deepcopy(self.time)
        time["post_stamp"] = {"needed": True, "reason_code": "time.user_confirmed_no_overlay_present",
                              "requires_user_notice": True}
        report = self._final(time=time, observation_facts=None)
        self.assertEqual("UNKNOWN", self._outcomes(report)["package.time.post_stamp_applied"])
        self.assertEqual("UNKNOWN", report["overall"])

    def test_c_missing_situation_response_is_still_unknown(self):
        record = deepcopy(self.record)
        record.pop("situation_response")
        report = self._final(record=record)
        self.assertEqual("UNKNOWN", self._outcomes(report)["package.evidence.situation_response"])
        self.assertEqual("UNKNOWN", report["overall"])

    # --- PLATE_IMAGE는 선택 첨부로 남는다 --------------------------------------------------------

    def test_plate_image_stays_optional(self):
        assets = [item for item in self.assets if item.get("derived_role") != "PLATE_IMAGE"]
        report = self._final(assets=assets)
        self.assertEqual("PASS", report["overall"])
        package = self._package(report, assets=assets)
        self.assertEqual([], validate_contract(package))
        self.assertIn("plate_image_ref", self._package(self._final())["assets"])  # 있으면 싣는다
        self.assertNotIn("plate_image_ref", package["assets"])


if __name__ == "__main__":
    unittest.main()
