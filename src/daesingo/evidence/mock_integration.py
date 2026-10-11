"""Executable fixture adapter for the four shared evidence scenarios.

This module is test tooling. It loads shared upstream contract payloads, calls
the public pure functions, and records a consumer-shaped read. It never treats
scenario_id as a domain input and never returns a pre-recorded result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from .assembly import assemble_evidence, calculate_evidence_needs
from .errors import ContractInputError, PackageNotReady
from .policy import (
    GENERIC_NO_LOCATION_TEMPLATE_REF,
    GENERIC_TEMPLATE_REF,
    SAFETY_REPORT_POLICY_REF,
    SPECIFIC_NO_LOCATION_TEMPLATE_REF,
    SPECIFIC_TEMPLATE_REF,
    render_report,
)
from .requirements import build_report_package, evaluate_requirements
from .time_resolution import resolve_time
from .validation import validate_contract

Contract = dict[str, Any]
SCENARIOS = (
    "scenario_happy_001",
    "scenario_unknown_abstain_partial_001",
    "scenario_plate_reread_001",
    "scenario_correction_rerun_001",
)
PACKAGE_VERSION_DIFFERENCE = "The executable Package uses report-package/v1.2 and safety-report-policy/v1.2 (ADR-EVIDENCE-008); the I2-owned shared package still records report-package/v1.1 and safety-report-policy/v1.1. Only these version labels differ; the rendered report and report_inputs match."
_IMPLEMENTATION_FILES = (
    "src/daesingo/evidence/__init__.py",
    "src/daesingo/evidence/_contract.py",
    "src/daesingo/evidence/assembly.py",
    "src/daesingo/evidence/corrections.py",
    "src/daesingo/evidence/deadline.py",
    "src/daesingo/evidence/deadline_policy_v1.json",
    "src/daesingo/evidence/errors.py",
    "src/daesingo/evidence/mock_integration.py",
    "src/daesingo/evidence/attachment_policy_v1.json",
    "src/daesingo/evidence/policy.py",
    "src/daesingo/evidence/policy_data.json",
    "src/daesingo/evidence/policy_catalog.py",
    "src/daesingo/evidence/requirement_rules_v6.json",
    "src/daesingo/evidence/requirements.py",
    "src/daesingo/evidence/safety_report_policy_v1_2.json",
    "src/daesingo/evidence/time_resolution.py",
    "src/daesingo/evidence/validation.py",
    "tests/evidence/fixtures/adapter_inputs.json",
    "tests/evidence/test_contract_units.py",
    "tests/evidence/test_contract_validation.py",
    "tests/evidence/test_mock_integration.py",
    "tests/evidence/test_policy_decisions.py",
)


def _load(path: Path) -> Contract:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, value: Contract) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _fingerprints(root: Path) -> Contract:
    return {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest()
        for path in _IMPLEMENTATION_FILES
    }


def _upstream(root: Path, scenario_id: str) -> Contract:
    return {
        module: _load(root / "data" / "mock" / module / f"{scenario_id}.json")
        for module in ("recording", "search", "readout", "case")
    }


def _selected_candidate(search: Contract, case: Contract) -> Contract:
    selected = [item for item in case["case_views"][-1].get("candidates", []) if item.get("selected")]
    if len(selected) != 1:
        raise ValueError("fixture adapter needs exactly one selected candidate")
    candidate_id = selected[0]["candidate_id"]
    candidates = [
        item
        for group in search["analysis_run_candidate_events"]
        for item in group["candidates"]
        if item["candidate_id"] == candidate_id
    ]
    if len(candidates) != 1:
        raise ValueError("selected candidate is not uniquely present in search output")
    return candidates[0]


def _visual(search: Contract, candidate_id: str) -> Contract:
    values = [item for item in search["visual_evidences"] if item.get("candidate_id") == candidate_id]
    if len(values) != 1:
        raise ValueError("fixture adapter needs one VisualEvidence")
    fine_run_ids = {
        group["analysis_run"]["run_id"]
        for group in search["analysis_run_candidate_events"]
        if group["analysis_run"]["operation"] == "VISUAL_VERIFY"
    }
    if values[0]["run_id"] not in fine_run_ids:
        raise ValueError("VisualEvidence does not retain its Fine run")
    return values[0]


def _clip(recording: Contract, clip_id: str) -> Contract:
    values = [item for item in recording["incident_clips"] if item["incident_clip_ref"] == clip_id]
    if len(values) != 1:
        raise ValueError("fixture adapter needs one IncidentClip")
    return values[0]


def _head(values: list[Contract], ref_field: str) -> Contract | None:
    if not values:
        return None
    superseded = {
        value["supersedes_ref"]["ref"]
        for value in values
        if isinstance(value.get("supersedes_ref"), dict)
    }
    heads = [value for value in values if value[ref_field]["ref"] not in superseded]
    if len(heads) != 1:
        raise ValueError(f"expected one head for {ref_field}")
    return heads[0]


def consume_contracts(outputs: Contract) -> Contract:
    """Minimal case-shaped read; this is not a CaseView projection."""
    all_values = [
        *outputs["time_resolutions"],
        *outputs["evidence_records"],
        *outputs["evidence_needs"],
        *outputs["requirement_reports"],
        *outputs["report_packages"],
    ]
    validation_errors = [
        {"ref": value.get("resolution_ref") or value.get("record_ref") or value.get("basis_record_ref") or value.get("requirement_report_ref") or value.get("package_ref"), "errors": errors}
        for value in all_values
        if (errors := validate_contract(value))
    ]
    if validation_errors:
        raise ValueError(f"contract validation failed: {validation_errors}")

    current = _head(outputs["evidence_records"], "record_ref")
    if current is None:
        return {"current_evidence_ref": None, "evidence_sufficient": False, "package_ready": False}
    current_ref = current["record_ref"]["ref"]
    reports = [
        item
        for item in outputs["requirement_reports"]
        if item["basis"]["evidence_record_ref"]["ref"] == current_ref
    ]
    evidence_report = _head([item for item in reports if item["scope"] == "EVIDENCE"], "requirement_report_ref")
    package_report = _head([item for item in reports if item["scope"] == "FINAL_PACKAGE"], "requirement_report_ref")
    packages = [
        item
        for item in outputs["report_packages"]
        if package_report is not None
        and item["evidence_record_ref"]["ref"] == current_ref
        and item["requirement_report_ref"] == package_report["requirement_report_ref"]
    ]
    return {
        "current_evidence_ref": current_ref,
        "time_resolution_ref": current.get("occurred_at", {}).get("time_resolution_ref"),
        "evidence_requirement_ref": None if evidence_report is None else evidence_report["requirement_report_ref"],
        "package_requirement_ref": None if package_report is None else package_report["requirement_report_ref"],
        "report_package_ref": None if not packages else packages[0]["package_ref"],
        "evidence_sufficient": bool(evidence_report and evidence_report["overall"] in {"PASS", "WARN"}),
        "package_ready": bool(package_report and package_report["overall"] in {"PASS", "WARN"} and packages),
        "user_reviewed": "CASE_OWNED_NOT_DERIVED",
    }


def _assemble(
    *, upstream: Contract, config: Contract, time: Contract, plate: Contract | None, record_id: str,
    supersedes_id: str | None = None, correction_records: list[Contract] | None = None
) -> Contract:
    candidate = _selected_candidate(upstream["search"], upstream["case"])
    visual = _visual(upstream["search"], candidate["candidate_id"])
    clip_id = plate["input_ref"]["incident_clip_ref"] if plate else upstream["recording"]["incident_clips"][0]["incident_clip_ref"]
    latest_view = upstream["case"]["case_views"][-1]
    gps_values = upstream["recording"].get("gps_observations") or []
    return assemble_evidence(
        case_id=latest_view["case_id"],
        selection_rev=config["selection_rev"],
        candidate_event=candidate,
        visual_evidence=visual,
        time_resolution=time,
        plate_readout=plate,
        incident_clip=_clip(upstream["recording"], clip_id),
        record_id=record_id,
        supersedes_id=supersedes_id,
        location_hint=latest_view.get("hints", {}).get("location"),
        gps_observation=gps_values[0] if gps_values else None,
        situation_response=config.get("situation_response"),
        correction_records=correction_records,
    )


def _render_preview(record: Contract) -> Contract | None:
    location = record.get("location") or {}
    display = next((location[key]["value"] for key in ("address", "place_name", "user_hint") if location.get(key)), None)
    if record.get("occurred_at") is None or record.get("vehicle_number") is None:
        return None
    event = record["event"]
    return render_report(
        visual_event_type=event["visual_event_type"]["value"],
        situation_response=record.get("situation_response", {}).get("value"),
        occurred_at=record["occurred_at"]["value"],
        location_display=display,
        vehicle_number=record["vehicle_number"]["value"],
        violation_expression=event["violation_expression"]["value"],
    )


def _base(root: Path, scenario_id: str, config: Contract) -> tuple[Contract, Contract, Contract, Contract, Contract]:
    upstream = _upstream(root, scenario_id)
    candidate = _selected_candidate(upstream["search"], upstream["case"])
    overlay_values = upstream["readout"].get("overlay_time_readouts") or []
    overlay = overlay_values[0] if overlay_values else None
    clip_id = overlay["input_ref"]["incident_clip_ref"] if overlay else upstream["recording"]["incident_clips"][0]["incident_clip_ref"]
    clip = _clip(upstream["recording"], clip_id)
    latest_view = upstream["case"]["case_views"][-1]
    return upstream, candidate, overlay, clip, latest_view


def run_scenario(root: Path, scenario_id: str, config: Contract) -> Contract:
    upstream, candidate, overlay, clip, latest_view = _base(root, scenario_id, config)
    ids = config["output_ids"]
    times: list[Contract] = []
    records: list[Contract] = []
    needs: list[Contract] = []
    reports: list[Contract] = []
    packages: list[Contract] = []
    package_error: str | None = None
    policy_guard_check: Contract | None = None
    corrections = upstream["case"].get("correction_records") or []
    plates = upstream["readout"].get("plate_readouts") or []

    if scenario_id == "scenario_correction_rerun_001":
        time_v1 = resolve_time(
            time_source_candidates=upstream["recording"]["time_source_candidates"],
            overlay_time_readout=overlay,
            candidate_event=candidate,
            case_id=latest_view["case_id"],
            selection_rev=config["selection_rev"],
            resolution_id=ids["time"][0],
        )
        record_v1 = _assemble(upstream=upstream, config=config, time=time_v1, plate=plates[0], record_id=ids["evidence"][0])
        report_v1 = evaluate_requirements(
            record_v1,
            scope="EVIDENCE",
            report_id=ids["requirements"][0],
            evaluated_at=config["evaluated_at"][0],
            time_resolution=time_v1,
        )
        time_v2 = resolve_time(
            time_source_candidates=upstream["recording"]["time_source_candidates"],
            overlay_time_readout=overlay,
            candidate_event=candidate,
            correction_records=corrections,
            case_id=latest_view["case_id"],
            selection_rev=config["selection_rev"],
            resolution_id=ids["time"][1],
            supersedes_id=ids["time"][0],
        )
        record_v2 = _assemble(
            upstream=upstream,
            config=config,
            time=time_v2,
            plate=plates[0],
            record_id=ids["evidence"][1],
            supersedes_id=ids["evidence"][0],
            correction_records=corrections,
        )
        report_v2 = evaluate_requirements(
            record_v2,
            scope="EVIDENCE",
            report_id=ids["requirements"][1],
            evaluated_at=config["evaluated_at"][1],
            time_resolution=time_v2,
            supersedes_id=ids["requirements"][0],
        )
        times.extend((time_v1, time_v2))
        records.extend((record_v1, record_v2))
        reports.extend((report_v1, report_v2))
        needs.append(calculate_evidence_needs(record_v2, plates[0], emit_empty=True))
    elif scenario_id == "scenario_plate_reread_001":
        time = resolve_time(
            time_source_candidates=upstream["recording"]["time_source_candidates"],
            overlay_time_readout=overlay,
            candidate_event=candidate,
            case_id=latest_view["case_id"],
            selection_rev=config["selection_rev"],
            resolution_id=ids["time"][0],
        )
        record_v1 = _assemble(upstream=upstream, config=config, time=time, plate=plates[0], record_id=ids["evidence"][0])
        record_v2 = _assemble(
            upstream=upstream,
            config=config,
            time=time,
            plate=plates[1],
            record_id=ids["evidence"][1],
            supersedes_id=ids["evidence"][0],
        )
        needs.extend(
            (
                calculate_evidence_needs(record_v1, plates[0], emit_empty=True),
                calculate_evidence_needs(record_v2, plates[1], emit_empty=True),
            )
        )
        reports.extend(
            (
                evaluate_requirements(
                    record_v1,
                    scope="EVIDENCE",
                    report_id=ids["requirements"][0],
                    evaluated_at=config["evaluated_at"][0],
                    time_resolution=time,
                ),
                evaluate_requirements(
                    record_v2,
                    scope="EVIDENCE",
                    report_id=ids["requirements"][1],
                    evaluated_at=config["evaluated_at"][1],
                    time_resolution=time,
                ),
            )
        )
        times.append(time)
        records.extend((record_v1, record_v2))
    else:
        time = resolve_time(
            time_source_candidates=upstream["recording"]["time_source_candidates"],
            overlay_time_readout=overlay,
            candidate_event=candidate,
            case_id=latest_view["case_id"],
            selection_rev=config["selection_rev"],
            resolution_id=ids["time"][0],
        )
        plate = plates[0] if plates else None
        if scenario_id == "scenario_happy_001":
            unconfirmed_config = deepcopy(config)
            unconfirmed_config.pop("situation_response", None)
            unconfirmed_record = _assemble(
                upstream=upstream,
                config=unconfirmed_config,
                time=time,
                plate=plate,
                record_id=f"{ids['evidence'][0]}_unconfirmed_guard",
            )
            render_error: str | None = None
            try:
                _render_preview(unconfirmed_record)
            except ContractInputError as exc:
                render_error = str(exc)
            if render_error != "report.input.situation_unconfirmed":
                raise ValueError("specific-template policy guard did not fail closed")
            policy_guard_check = {
                "shared_case_situation_confirmation": next(
                    item["situation_confirmation"]
                    for item in latest_view["candidates"]
                    if item.get("selected")
                ),
                "without_confirmation": {
                    "evidence_record": unconfirmed_record,
                    "render_error": render_error,
                    "normal_final_report_emitted": False,
                    "report_package_emitted": False,
                },
                "with_derived_confirmation": {
                    "adapter_input": deepcopy(config.get("situation_response")),
                    "derivation": deepcopy(config.get("derived_case_context")),
                },
            }
        record = _assemble(upstream=upstream, config=config, time=time, plate=plate, record_id=ids["evidence"][0])
        need = calculate_evidence_needs(record, plate, emit_empty=config["emit_empty_needs"])
        if need:
            needs.append(need)
        evidence_report = evaluate_requirements(
            record,
            scope="EVIDENCE",
            report_id=ids["requirements"][0],
            evaluated_at=config["evaluated_at"][0],
            time_resolution=time,
        )
        final_report = evaluate_requirements(
            record,
            scope="FINAL_PACKAGE",
            report_id=ids["requirements"][1],
            evaluated_at=config["evaluated_at"][1],
            time_resolution=time,
            asset_facts=upstream["recording"].get("asset_facts") or [],
            observation_facts=config["requirement_observation_facts"],
        )
        try:
            package = build_report_package(
                record,
                final_report,
                package_id=ids["package"],
                created_at=config["package_created_at"],
                asset_facts=upstream["recording"].get("asset_facts") or [],
            )
            packages.append(package)
        except PackageNotReady as exc:
            package_error = exc.code
        times.append(time)
        records.append(record)
        reports.extend((evidence_report, final_report))

    expected_rules = config["evidence_rules"]
    for report in [item for item in reports if item["scope"] == "EVIDENCE"]:
        if [item["code"] for item in report["checks"]] != expected_rules:
            raise ValueError("active EVIDENCE catalog selection differs from adapter expectation")
    final_reports = [item for item in reports if item["scope"] == "FINAL_PACKAGE"]
    if final_reports and [item["code"] for item in final_reports[-1]["checks"]] != config["final_rules"]:
        raise ValueError("active FINAL_PACKAGE catalog selection differs from adapter expectation")

    outputs = {
        "time_resolutions": times,
        "evidence_records": records,
        "evidence_needs": needs,
        "requirement_reports": reports,
        "report_packages": packages,
    }
    expected = _load(root / "data" / "mock" / "evidence" / f"{scenario_id}.json")
    expected_overalls = [item["overall"] for item in expected["requirement_reports"]]
    actual_overalls = [item["overall"] for item in reports]
    comparison: Contract = {
        "common_fixture_ref": f"data/mock/evidence/{scenario_id}.json",
        "time_statuses_match": [item["status"] for item in times] == [item["status"] for item in expected["time_resolutions"]],
        "requirement_overalls_match": actual_overalls == expected_overalls,
        "common_package_count": len(expected["report_packages"]),
        "baseline_package_count": len(packages),
        "known_differences": [],
    }
    if scenario_id == "scenario_happy_001":
        comparison["known_differences"].append("The shared fixture records the pre-response ev_h001 (FINAL_PACKAGE UNKNOWN) superseded by the CONFIRMED ev_h001_v2; the executable baseline assembles one CONFIRMED record from the adapter response, so requirement overalls and the Package evidence/requirement refs differ while the rendered Package content matches. The guard result preserves the pre-response path.")
        comparison["known_differences"].append(PACKAGE_VERSION_DIFFERENCE)
    if scenario_id == "scenario_unknown_abstain_partial_001":
        comparison["known_differences"].append(PACKAGE_VERSION_DIFFERENCE)
        comparison["known_differences"].append("The no-location generic renderer omits the location phrase and never invents a location value.")

    return {
        "artifact_version": "evidence-first-completion/v1",
        "scenario_id": scenario_id,
        "execution_mode": {
            "core": "BASELINE_PURE_FUNCTIONS",
            "upstream": "SHARED_MOCK_CONTRACTS",
            "requirement_observations": "EVIDENCE_TEST_MOCK",
            "consumer": "CONTRACT_READER_MOCK",
            "case_context": "EVIDENCE_TEST_DERIVED" if config.get("derived_case_context") else "SHARED_CASE_CONTRACTS",
        },
        "versions": {
            "contracts": [
                "time-resolution/v1",
                "evidence-record/v1.3",
                "evidence-needs/v1",
                "requirement-report/v1",
                "report-package/v1.2",
                "correction-record/v1.1",
            ],
            "safety_report_policy": SAFETY_REPORT_POLICY_REF,
            "specific_template": SPECIFIC_TEMPLATE_REF,
            "generic_template": GENERIC_TEMPLATE_REF,
            "specific_no_location_template": SPECIFIC_NO_LOCATION_TEMPLATE_REF,
            "generic_no_location_template": GENERIC_NO_LOCATION_TEMPLATE_REF,
        },
        "source_paths": {
            module: f"data/mock/{module}/{scenario_id}.json" for module in ("recording", "search", "readout", "case")
        },
        "adapter_input_ref": "tests/evidence/fixtures/adapter_inputs.json",
        "input_trace": {
            "case_id": latest_view["case_id"],
            "candidate_id": candidate["candidate_id"],
            "candidate_fine_run_ref": _visual(upstream["search"], candidate["candidate_id"])["run_id"],
            "timeline_ref": deepcopy(clip["source_provenance"]["timeline_ref"]),
            "timeline_range": deepcopy(clip["source_provenance"]["requested_range"]),
            "selection_rev": config["selection_rev"],
            "correction_refs": [item["correction_id"] for item in corrections],
        },
        "outputs": outputs,
        "package_boundary_error": package_error,
        "policy_guard_check": policy_guard_check,
        "consumer_mock": consume_contracts(outputs),
        "comparison": comparison,
    }


def run_all(root: Path, output_dir: Path) -> Contract:
    configs = _load(root / "tests" / "evidence" / "fixtures" / "adapter_inputs.json")["scenarios"]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    fingerprints = _fingerprints(root)
    results = []
    for scenario_id in SCENARIOS:
        result = run_scenario(root, scenario_id, configs[scenario_id])
        result["base_revision"] = revision
        result["implementation_fingerprints"] = fingerprints
        _write(output_dir / f"{scenario_id}.baseline.json", result)
        results.append(
            {
                "scenario_id": scenario_id,
                "time": [item["status"] for item in result["outputs"]["time_resolutions"]],
                "evidence": [item["record_ref"]["ref"] for item in result["outputs"]["evidence_records"]],
                "requirements": [item["overall"] for item in result["outputs"]["requirement_reports"]],
                "package_count": len(result["outputs"]["report_packages"]),
                "package_boundary_error": result["package_boundary_error"],
                "policy_guard": None
                if result["policy_guard_check"] is None
                else {
                    "shared_case_situation_confirmation": result["policy_guard_check"]["shared_case_situation_confirmation"],
                    "without_confirmation": {
                        "render_error": result["policy_guard_check"]["without_confirmation"]["render_error"],
                        "normal_final_report_emitted": result["policy_guard_check"]["without_confirmation"]["normal_final_report_emitted"],
                        "report_package_emitted": result["policy_guard_check"]["without_confirmation"]["report_package_emitted"],
                    },
                    "with_derived_confirmation": result["policy_guard_check"]["with_derived_confirmation"],
                },
                "consumer_mock": result["consumer_mock"],
            }
        )
    summary = {
        "artifact_version": "evidence-first-completion-summary/v1",
        "base_revision": revision,
        "implementation_fingerprints": fingerprints,
        "scenarios": results,
        "readiness": "PARTIAL_READY",
        "reason": "Shared upstream contracts and a consumer reader are executable; H/U Package assembly succeeds under requirement-rules-v6, which no longer requires the I4 final-video plate/time observations (ADR-EVIDENCE-010), while real case projection and the post-stamp fact wiring remain unconnected.",
    }
    _write(output_dir / "run-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="artifact directory; defaults to docs/modules/evidence/artifacts/first-completion",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    output_dir = args.output_dir or root / "docs" / "modules" / "evidence" / "artifacts" / "first-completion"
    summary = run_all(root, output_dir.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
