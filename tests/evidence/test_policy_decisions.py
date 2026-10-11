from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from daesingo.evidence import (
    PackageNotReady,
    PolicyConfigurationError,
    build_report_package,
    evaluate_requirements,
    validate_contract,
)
from daesingo.evidence import requirements as requirement_module
from daesingo.evidence.mock_integration import run_scenario
from daesingo.evidence.policy_catalog import (
    load_attachment_policy,
    load_deadline_policy,
    load_requirement_catalog,
    validate_attachment_policy,
    validate_deadline_policy,
    validate_report_policy,
    validate_requirement_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = json.loads((ROOT / "tests/evidence/fixtures/adapter_inputs.json").read_text(encoding="utf-8"))["scenarios"]


class PolicyDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.happy = run_scenario(ROOT, "scenario_happy_001", CONFIGS["scenario_happy_001"])
        cls.unknown = run_scenario(ROOT, "scenario_unknown_abstain_partial_001", CONFIGS["scenario_unknown_abstain_partial_001"])
        cls.happy_record = cls.happy["outputs"]["evidence_records"][0]
        cls.happy_time = cls.happy["outputs"]["time_resolutions"][0]
        cls.happy_assets = json.loads((ROOT / "data/mock/recording/scenario_happy_001.json").read_text(encoding="utf-8"))["asset_facts"]
        cls.unknown_assets = json.loads((ROOT / "data/mock/recording/scenario_unknown_abstain_partial_001.json").read_text(encoding="utf-8"))["asset_facts"]

    def _facts(self, scenario: str = "happy"):
        return deepcopy(CONFIGS[
            "scenario_happy_001" if scenario == "happy" else "scenario_unknown_abstain_partial_001"
        ]["requirement_observation_facts"])

    def _evaluate(self, *, record=None, time=None, assets=None, facts=None,
                  evaluated_at="2026-08-24T18:25:00+09:00", report_id="req_policy_unit"):
        return evaluate_requirements(
            record or self.happy_record,
            scope="FINAL_PACKAGE",
            report_id=report_id,
            evaluated_at=evaluated_at,
            time_resolution=time or self.happy_time,
            asset_facts=self.happy_assets if assets is None else assets,
            observation_facts=self._facts() if facts is None else facts,
        )

    @staticmethod
    def _check(report, code):
        return next(item for item in report["checks"] if item["code"] == code)

    def test_k1_exact_limit_one_byte_over_and_null_measurement(self):
        exact = deepcopy(self.happy_assets)
        next(item for item in exact if item.get("derived_role") == "REPORT_VIDEO")["byte_size"] = 130_000_000
        exact_check = self._check(self._evaluate(assets=exact), "package.asset.video.each_size")
        self.assertEqual(("PASS", 130_000_000, 130_000_000, "asset.bytes"), (
            exact_check["outcome"], exact_check["measurement"]["actual"],
            exact_check["measurement"]["limit"], exact_check["measurement"]["unit"]))

        over = deepcopy(exact)
        next(item for item in over if item.get("derived_role") == "REPORT_VIDEO")["byte_size"] += 1
        self.assertEqual("BLOCK", self._check(
            self._evaluate(assets=over), "package.asset.video.each_size")["outcome"])

        unknown = deepcopy(self.happy_assets)
        next(item for item in unknown if item.get("derived_role") == "PLATE_IMAGE")["byte_size"] = None
        image = self._check(self._evaluate(assets=unknown), "package.asset.image.each_size")
        self.assertEqual("UNKNOWN", image["outcome"])
        self.assertEqual({"actual": 0, "limit": 30_000_000, "unit": "asset.bytes"}, image["measurement"])

    def test_k1_partial_total_distinguishes_block_from_unknown(self):
        partial = deepcopy(self.happy_assets)
        video = next(item for item in partial if item.get("derived_role") == "REPORT_VIDEO")
        image = next(item for item in partial if item.get("derived_role") == "PLATE_IMAGE")
        video["byte_size"], image["byte_size"] = 170_000_000, None
        self.assertEqual("UNKNOWN", self._check(
            self._evaluate(assets=partial), "package.asset.total_size")["outcome"])
        video["byte_size"] = 180_000_001
        total = self._check(self._evaluate(assets=partial), "package.asset.total_size")
        self.assertEqual("BLOCK", total["outcome"])
        self.assertEqual(180_000_001, total["measurement"]["actual"])

    def test_k1_count_rules_deduplicate_and_cover_each_kind(self):
        duplicated = deepcopy(self.happy_assets)
        duplicated.append(deepcopy(next(item for item in duplicated if item.get("derived_role") == "PLATE_IMAGE")))
        report = self._evaluate(assets=duplicated)
        counts = {code: self._check(report, code) for code in (
            "package.asset.image.count", "package.asset.video.count", "package.asset.total_count")}
        self.assertEqual((1, 1, 2), tuple(item["measurement"]["actual"] for item in counts.values()))
        self.assertTrue(all(item["outcome"] == "PASS" for item in counts.values()))

        base_video = deepcopy(next(item for item in self.happy_assets if item.get("derived_role") == "REPORT_VIDEO"))
        images = []
        for index in range(5):
            item = deepcopy(next(item for item in self.happy_assets if item.get("derived_role") == "PLATE_IMAGE"))
            item["asset_ref"] = {"kind": "derived_asset", "ref": f"plate_{index}"}
            images.append(item)
        image_report = self._evaluate(assets=[base_video, *images])
        self.assertEqual("BLOCK", self._check(image_report, "package.asset.image.count")["outcome"])
        self.assertEqual("BLOCK", self._check(image_report, "package.asset.total_count")["outcome"])

        videos = []
        for index in range(5):
            item = deepcopy(base_video)
            item["asset_ref"] = {"kind": "derived_asset", "ref": f"video_{index}"}
            videos.append(item)
        video_report = self._evaluate(assets=videos)
        self.assertEqual("BLOCK", self._check(video_report, "package.asset.video.count")["outcome"])
        self.assertEqual("BLOCK", self._check(video_report, "package.asset.total_count")["outcome"])

        image_only = [images[0]]
        incomplete = self._evaluate(assets=image_only)
        self.assertTrue(all(self._check(incomplete, code)["outcome"] == "UNKNOWN" for code in counts))

    def test_k1_policy_missing_or_malformed_emits_no_report(self):
        malformed = load_attachment_policy()
        malformed["limits"].pop("total_bytes")
        with self.assertRaises(PolicyConfigurationError):
            validate_attachment_policy(malformed)
        with (
            patch.object(
                requirement_module,
                "load_attachment_policy",
                side_effect=PolicyConfigurationError("missing K1 policy"),
            ),
            self.assertRaises(PolicyConfigurationError),
        ):
            self._evaluate()

    def _deadline_case(self, occurred_at, evaluated_at, *, status="OK"):
        record = deepcopy(self.happy_record)
        time = deepcopy(self.happy_time)
        record["occurred_at"]["value"] = occurred_at
        record["occurred_at"]["resolution_status"] = status
        time["status"] = status
        time["post_stamp"] = {
            "needed": status != "OK",
            "reason_code": "time.verified_overlay_already_present" if status == "OK" else "time.no_verified_overlay_present",
            "requires_user_notice": status != "OK",
        }
        report = self._evaluate(record=record, time=time, evaluated_at=evaluated_at)
        return self._check(report, "package.deadline.within_policy")

    def test_k2_weekday_friday_consecutive_holidays_and_year_boundary(self):
        cases = (
            ("2026-03-03T10:00:00+09:00", "2026-03-05T12:00:00+09:00", "2026-03-05", "OPEN"),
            ("2026-03-06T10:00:00+09:00", "2026-03-09T12:00:00+09:00", "2026-03-09", "EXTENDED"),
            ("2026-09-23T10:00:00+09:00", "2026-09-28T12:00:00+09:00", "2026-09-28", "EXTENDED"),
            ("2026-12-30T10:00:00+09:00", "2027-01-04T12:00:00+09:00", "2027-01-04", "EXTENDED"),
        )
        for occurred, evaluated, deadline, status in cases:
            with self.subTest(occurred=occurred):
                check = self._deadline_case(occurred, evaluated)
                self.assertEqual("PASS", check["outcome"])
                self.assertEqual(deadline, check["provenance"]["deadline_date"])
                self.assertEqual(status, check["provenance"]["deadline_status"])

    def test_k2_exclusive_boundary_and_status_mapping(self):
        before = self._deadline_case("2026-03-03T10:00:00+09:00", "2026-03-05T23:59:59.999000+09:00")
        exact = self._deadline_case("2026-03-03T10:00:00+09:00", "2026-03-06T00:00:00+09:00")
        after = self._deadline_case("2026-03-03T10:00:00+09:00", "2026-03-06T00:00:01+09:00")
        review = self._deadline_case("2026-03-03T10:00:00+09:00", "2026-03-05T12:00:00+09:00",
                                     status="NEEDS_REVIEW")
        self.assertEqual(("PASS", "WARN", "WARN", "WARN"), tuple(
            item["outcome"] for item in (before, exact, after, review)))
        self.assertEqual("deadline.time_needs_review", review["reason_code"])
        self.assertEqual("policy/safety-report-deadline/v1", exact["provenance"]["policy_ref"])
        self.assertEqual("calendar/kr-public-holidays/2026-2027/r1", exact["provenance"]["calendar_ref"])

    def test_k2_missing_unknown_and_bad_coverage(self):
        record = deepcopy(self.happy_record)
        record.pop("occurred_at")
        time = deepcopy(self.happy_time)
        time["status"] = "UNKNOWN"
        time["post_stamp"] = {"needed": False, "reason_code": "time.no_resolvable_source",
                              "requires_user_notice": True}
        check = self._check(self._evaluate(record=record, time=time), "package.deadline.within_policy")
        self.assertEqual("UNKNOWN", check["outcome"])

        with self.assertRaises(PolicyConfigurationError):
            self._deadline_case("2027-12-31T10:00:00+09:00", "2027-12-31T12:00:00+09:00")
        malformed = load_deadline_policy()
        malformed["holidays"].pop("2027")
        with self.assertRaises(PolicyConfigurationError):
            validate_deadline_policy(malformed)

    def test_k3_catalog_selects_four_and_eleven_rules_from_data(self):
        # H는 검증된 overlay 갈래라 v6에서 시각 표시 rule이 붙지 않는다(ADR-EVIDENCE-010): 무조건 11 + 0.
        evidence = evaluate_requirements(
            self.happy_record, scope="EVIDENCE", report_id="req_catalog_evidence",
            evaluated_at="2026-08-24T18:23:00+09:00", time_resolution=self.happy_time)
        final = self._evaluate()
        self.assertEqual(4, len(evidence["checks"]))
        self.assertEqual(11, len(final["checks"]))
        self.assertEqual(CONFIGS["scenario_happy_001"]["evidence_rules"],
                         [item["code"] for item in evidence["checks"]])
        self.assertEqual(CONFIGS["scenario_happy_001"]["final_rules"],
                         [item["code"] for item in final["checks"]])
        self.assertEqual(load_requirement_catalog()["policy_ref"], final["policy_ref"])

    def test_k3_time_selector_covers_all_four_branches(self):
        # v6: 검증된 overlay 갈래는 선택되지만 rule이 없다 — 최종 영상 관찰(I4)을 요구하지 않는다(#280).
        cases = (
            ("OK", "time.verified_overlay_already_present", [], True),
            ("OK", "time.user_confirmed_no_overlay_present", ["package.time.post_stamp_applied"], True),
            ("NEEDS_REVIEW", "time.no_verified_overlay_present", ["package.time.post_stamp_applied"], True),
            ("UNKNOWN", "time.no_resolvable_source", ["package.time.display_unresolved"], False),
        )
        for index, (status, reason, expected, has_occurred) in enumerate(cases):
            with self.subTest(status=status, reason=reason):
                record, time = deepcopy(self.happy_record), deepcopy(self.happy_time)
                time["status"] = status
                time["post_stamp"] = {"needed": reason != "time.verified_overlay_already_present",
                                      "reason_code": reason, "requires_user_notice": status != "OK"}
                if has_occurred:
                    record["occurred_at"]["resolution_status"] = status
                else:
                    record.pop("occurred_at")
                report = self._evaluate(record=record, time=time, report_id=f"req_selector_{index}")
                selected = [item["code"] for item in report["checks"] if item["code"].startswith("package.time.")]
                self.assertEqual(expected, selected)

    def test_k3_configuration_errors_emit_no_normal_report(self):
        catalog = load_requirement_catalog()
        bad_ref = deepcopy(catalog)
        bad_ref["referenced_policies"]["attachment"] = "policy/missing"
        with (
            patch.object(
                requirement_module, "load_requirement_catalog", return_value=bad_ref
            ),
            self.assertRaises(PolicyConfigurationError),
        ):
            self._evaluate()

        unsupported = deepcopy(catalog)
        unsupported["scopes"]["EVIDENCE"]["always"][0]["code"] = "evidence.unsupported"
        with (
            patch.object(
                requirement_module,
                "load_requirement_catalog",
                return_value=unsupported,
            ),
            self.assertRaises(PolicyConfigurationError),
        ):
            evaluate_requirements(self.happy_record, scope="EVIDENCE", report_id="bad",
                                  evaluated_at="2026-08-24T18:23:00+09:00",
                                  time_resolution=self.happy_time)

        for mutation in ("empty", "duplicate"):
            broken = deepcopy(catalog)
            rules = broken["scopes"]["EVIDENCE"]["always"]
            broken["scopes"]["EVIDENCE"]["always"] = [] if mutation == "empty" else [*rules, deepcopy(rules[0])]
            with (
                patch.object(
                    requirement_module,
                    "load_requirement_catalog",
                    return_value=broken,
                ),
                self.assertRaises(PolicyConfigurationError),
            ):
                evaluate_requirements(self.happy_record, scope="EVIDENCE", report_id=f"bad_{mutation}",
                                      evaluated_at="2026-08-24T18:23:00+09:00",
                                      time_resolution=self.happy_time)

        invalid_record = deepcopy(self.happy_record)
        invalid_record["event"]["safety_report_type"]["value"] = "UNREGISTERED"
        with self.assertRaises(PolicyConfigurationError):
            evaluate_requirements(invalid_record, scope="EVIDENCE", report_id="bad_type",
                                  evaluated_at="2026-08-24T18:23:00+09:00",
                                  time_resolution=self.happy_time)

    def test_k3_selector_and_observation_configuration_errors(self):
        no_match = deepcopy(self.happy_time)
        no_match["post_stamp"]["reason_code"] = "time.unregistered"
        with self.assertRaises(PolicyConfigurationError):
            self._evaluate(time=no_match)

        catalog = load_requirement_catalog()
        duplicate = deepcopy(catalog["scopes"]["FINAL_PACKAGE"]["conditional"][0]["cases"][0])
        catalog["scopes"]["FINAL_PACKAGE"]["conditional"][0]["cases"].append(duplicate)
        with (
            patch.object(
                requirement_module, "load_requirement_catalog", return_value=catalog
            ),
            self.assertRaises(PolicyConfigurationError),
        ):
            self._evaluate()

        # 관찰 fact 구조 검증은 남은 관찰 rule(post_stamp_applied)에 그대로 적용된다.
        malformed_facts = self._facts("unknown")
        malformed_facts["post_stamp_applied"] = {"value": "yes"}
        with self.assertRaises(PolicyConfigurationError):
            evaluate_requirements(
                self.unknown["outputs"]["evidence_records"][0], scope="FINAL_PACKAGE",
                report_id="req_malformed_fact",
                evaluated_at=CONFIGS["scenario_unknown_abstain_partial_001"]["evaluated_at"][1],
                time_resolution=self.unknown["outputs"]["time_resolutions"][0],
                asset_facts=self.unknown_assets, observation_facts=malformed_facts)

        no_rule_with_code = load_requirement_catalog()
        branch = no_rule_with_code["scopes"]["FINAL_PACKAGE"]["conditional"][0]["cases"][0]
        self.assertTrue(branch["no_rule"])
        branch["code"] = "package.time.overlay_visible"
        with self.assertRaises(PolicyConfigurationError):
            validate_requirement_catalog(no_rule_with_code)

    def test_d2_removed_event_context_rules_are_absent_and_legacy_inputs_are_ignored(self):
        removed_codes = {
            "package.event.violation_visible_in_report_video",
            "package.event.pre_context_present",
            "package.event.post_context_present",
        }
        catalog = load_requirement_catalog()
        active_codes = {item["code"] for item in catalog["scopes"]["FINAL_PACKAGE"]["always"]}
        self.assertTrue(removed_codes.isdisjoint(active_codes))

        baseline = self._evaluate(report_id="req_d2_baseline")
        legacy_facts = self._facts()
        legacy_facts.update({
            "violation_visible_in_report_video": {"value": "legacy"},
            "pre_context_present_in_report_video": None,
            "post_context_present_in_report_video": ["legacy"],
        })
        with_legacy_inputs = self._evaluate(
            facts=legacy_facts, report_id="req_d2_legacy_inputs")
        self.assertEqual(baseline["overall"], with_legacy_inputs["overall"])
        self.assertEqual(baseline["checks"], with_legacy_inputs["checks"])

    def test_k3_not_asked_and_incomplete_render_are_unknown(self):
        record = deepcopy(self.happy_record)
        record.pop("situation_response")
        report = self._evaluate(record=record)
        self.assertEqual("UNKNOWN", self._check(
            report, "package.evidence.situation_response")["outcome"])
        self.assertEqual("UNKNOWN", self._check(
            report, "package.report.content_length")["outcome"])

    def test_invalid_vehicle_value_is_never_pass_and_splits_on_plate_readout_d3(self):
        # v4까지는 값이 없으면 전부 UNKNOWN이었다. #172 D-3(ADR-EVIDENCE-008 §5.1)부터는
        # PlateReadout이 있으면 WARN(판독했지만 못 읽음), 없으면 UNKNOWN(판독 결과 없음)이다.
        for invalid_value in (None, "", "  "):
            for with_readout in (True, False):
                with self.subTest(invalid_value=invalid_value, with_readout=with_readout):
                    record = deepcopy(self.happy_record)
                    record["vehicle_number"]["value"] = invalid_value
                    if not with_readout:
                        record["provenance"]["input_refs"] = [
                            ref for ref in record["provenance"]["input_refs"]
                            if ref["kind"] != "plate_readout"]
                    report = evaluate_requirements(
                        record,
                        scope="EVIDENCE",
                        report_id="req_invalid_vehicle",
                        evaluated_at="2026-08-24T18:23:00+09:00",
                        time_resolution=self.happy_time,
                    )
                    check = self._check(report, "evidence.vehicle_number.present")
                    expected = "WARN" if with_readout else "UNKNOWN"
                    self.assertEqual(expected, check["outcome"])
                    self.assertEqual(expected, report["overall"])

    def test_package_rejects_invalid_report_and_unevaluated_asset_refs(self):
        report = self._evaluate(report_id="req_package_gate")

        malformed = deepcopy(report)
        malformed["policy_ref"] = ""
        malformed["checks"] = [{"code": "not.a.real.rule", "outcome": "PASS"}]
        malformed["overall"] = "PASS"
        with self.assertRaisesRegex(
            PackageNotReady, "package.requirement_report_invalid"
        ):
            build_report_package(
                self.happy_record,
                malformed,
                package_id="pkg_invalid_report",
                created_at="2026-08-24T18:26:00+09:00",
                asset_facts=self.happy_assets,
            )

        replacement_assets = deepcopy(self.happy_assets)
        report_video = next(
            item for item in replacement_assets
            if item.get("derived_role") == "REPORT_VIDEO"
        )
        report_video["asset_ref"] = {
            "kind": "derived_asset",
            "ref": "da_unchecked_replacement",
        }
        report_video["byte_size"] = 999_999_999
        with self.assertRaisesRegex(
            PackageNotReady, "package.requirement_asset_basis_mismatch"
        ):
            build_report_package(
                self.happy_record,
                report,
                package_id="pkg_unevaluated_asset",
                created_at="2026-08-24T18:26:00+09:00",
                asset_facts=replacement_assets,
            )

        # #146 · #172 D-3: 판독 후 번호판을 못 읽은 기록은 번호판 없는 template으로 렌더된다.
        # 렌더 입력이 모자라 UNKNOWN이 되는 것은 PlateReadout 자체가 없을 때(실행 실패)뿐이다.
        for mutation in ("pop", "null"):
            with self.subTest(mutation=mutation):
                missing_plate = deepcopy(self.happy_record)
                if mutation == "pop":
                    missing_plate.pop("vehicle_number")
                else:
                    missing_plate["vehicle_number"]["value"] = None
                report = self._evaluate(record=missing_plate)
                self.assertEqual("PASS", self._check(
                    report, "package.report.content_length")["outcome"])
                self.assertEqual("tmpl/safety-report-specific-no-plate-v1", report["basis"]["template_ref"])

                missing_plate["provenance"]["input_refs"] = [
                    ref for ref in missing_plate["provenance"]["input_refs"] if ref["kind"] != "plate_readout"]
                report = self._evaluate(record=missing_plate)
                self.assertEqual("UNKNOWN", self._check(
                    report, "package.report.content_length")["outcome"])
                self.assertNotIn("template_ref", report["basis"])

    def test_location_snapshot_skips_empty_higher_priority_value(self):
        record = deepcopy(self.happy_record)
        record["location"]["address"] = {"value": None}
        record["location"]["place_name"] = {"value": "광화문 교차로"}
        report = self._evaluate(record=record)
        self.assertEqual("PASS", self._check(report, "package.location.present")["outcome"])
        self.assertEqual("PASS", self._check(report, "package.report.content_length")["outcome"])

    def test_d1_location_null_warn_package_and_template_are_reproducible(self):
        record = self.unknown["outputs"]["evidence_records"][0]
        time = self.unknown["outputs"]["time_resolutions"][0]
        report = evaluate_requirements(
            record, scope="FINAL_PACKAGE", report_id="req_u001_d1_unit",
            evaluated_at=CONFIGS["scenario_unknown_abstain_partial_001"]["evaluated_at"][1],
            time_resolution=time, asset_facts=self.unknown_assets,
            observation_facts=self._facts("unknown"))
        checks = {item["code"]: item for item in report["checks"]}
        self.assertEqual("WARN", checks["package.location.present"]["outcome"])
        self.assertEqual("PASS", checks["package.report.content_length"]["outcome"])
        self.assertEqual("WARN", report["overall"])
        package = build_report_package(
            record, report, package_id="pkg_u001_d1_unit", created_at="2026-08-26T22:36:00+09:00",
            asset_facts=self.unknown_assets)
        self.assertEqual([], validate_contract(package))
        self.assertIsNone(package["report_inputs"]["location"])
        self.assertEqual("report-package/v1.2", package["contract_version"])
        self.assertEqual("safety-report-policy/v1.2", package["provenance"]["policy_ref"])
        self.assertEqual("tmpl/safety-report-generic-no-location-v1", package["report"]["template_ref"])
        self.assertNotIn("위치 미상", package["report"]["description"])
        self.assertNotIn("발생장소", package["report"]["description"])

    def test_d1_both_catalog_changes_are_required(self):
        record = self.unknown["outputs"]["evidence_records"][0]
        time = self.unknown["outputs"]["time_resolutions"][0]
        kwargs = {
            "scope": "FINAL_PACKAGE", "report_id": "req_d1_guard",
            "evaluated_at": CONFIGS["scenario_unknown_abstain_partial_001"]["evaluated_at"][1],
            "time_resolution": time, "asset_facts": self.unknown_assets,
            "observation_facts": self._facts("unknown"),
        }
        catalog = load_requirement_catalog()
        location_only = deepcopy(catalog)
        location_rule = next(item for item in location_only["scopes"]["FINAL_PACKAGE"]["always"]
                             if item["code"] == "package.location.present")
        location_rule["outcomes"]["display_location_absent"] = "UNKNOWN"
        with patch.object(requirement_module, "load_requirement_catalog", return_value=location_only):
            self.assertEqual("UNKNOWN", evaluate_requirements(record, **kwargs)["overall"])

        template_only = deepcopy(catalog)
        content_rule = next(item for item in template_only["scopes"]["FINAL_PACKAGE"]["always"]
                            if item["code"] == "package.report.content_length")
        content_rule["render_required_inputs_by_template"]["without_location"].append(
            "package_display_location")
        with patch.object(requirement_module, "load_requirement_catalog", return_value=template_only):
            result = evaluate_requirements(record, **kwargs)
            self.assertEqual("UNKNOWN", result["overall"])
            self.assertEqual("UNKNOWN", self._check(
                result, "package.report.content_length")["outcome"])

    def test_policy_data_validators_reject_duplicate_and_incomplete_catalogs(self):
        catalog = load_requirement_catalog()
        duplicate = deepcopy(catalog)
        duplicate["scopes"]["EVIDENCE"]["always"][1]["code"] = duplicate["scopes"]["EVIDENCE"]["always"][0]["code"]
        with self.assertRaises(PolicyConfigurationError):
            validate_requirement_catalog(duplicate)
        incomplete = deepcopy(catalog)
        incomplete["scopes"]["FINAL_PACKAGE"]["always"].pop()
        with self.assertRaises(PolicyConfigurationError):
            validate_requirement_catalog(incomplete)
        malformed_outcome = deepcopy(catalog)
        malformed_outcome["scopes"]["EVIDENCE"]["always"][0]["outcomes"]["value_present"] = "ALLOW"
        with self.assertRaises(PolicyConfigurationError):
            validate_requirement_catalog(malformed_outcome)
        report_policy = validate_report_policy(
            json.loads((ROOT / "src/daesingo/evidence/safety_report_policy_v1_1.json").read_text(
                encoding="utf-8"
            ))
        )
        malformed_template = deepcopy(report_policy)
        malformed_template["generic_no_location_template_ref"] = ""
        with self.assertRaises(PolicyConfigurationError):
            validate_report_policy(malformed_template)


if __name__ == "__main__":
    unittest.main()
