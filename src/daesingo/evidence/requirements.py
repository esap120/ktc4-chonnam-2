"""RequirementReport evaluation and ready-only ReportPackage assembly."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from ._contract import Contract, contract_ref, parse_rfc3339, require
from .deadline import evaluate_deadline
from .errors import PackageNotReady, PolicyConfigurationError
from .policy import (
    GENERIC_NO_LOCATION_NO_PLATE_TEMPLATE_REF,
    GENERIC_NO_LOCATION_TEMPLATE_REF,
    GENERIC_NO_PLATE_TEMPLATE_REF,
    GENERIC_TEMPLATE_REF,
    REPORT_TEXT_MAX_LENGTH,
    REPORT_TEXT_MIN_LENGTH,
    SAFETY_REPORT_POLICY_REF,
    SPECIFIC_NO_LOCATION_NO_PLATE_TEMPLATE_REF,
    SPECIFIC_NO_LOCATION_TEMPLATE_REF,
    SPECIFIC_NO_PLATE_TEMPLATE_REF,
    SPECIFIC_TEMPLATE_REF,
    render_report,
    report_type_label,
)
from .policy_catalog import (
    load_attachment_policy,
    load_deadline_policy,
    load_requirement_catalog,
)
from .validation import validate_requirement_report

_PRECEDENCE = {"PASS": 0, "WARN": 1, "UNKNOWN": 2, "BLOCK": 3}
_PACKAGE_ROLES = {"REPORT_VIDEO", "PLATE_IMAGE"}
_SUPPORTED_RULES = {
    "evidence.vehicle_number.present", "evidence.occurred_at.present",
    "evidence.visual_event.present", "evidence.location.present",
    "package.asset.report_video.exists", "package.location.present",
    "package.report.content_length", "package.evidence.situation_response",
    "package.asset.image.each_size", "package.asset.video.each_size",
    "package.asset.total_size", "package.asset.image.count", "package.asset.video.count",
    "package.asset.total_count", "package.deadline.within_policy",
    "package.time.post_stamp_applied", "package.time.display_unresolved",
}


def aggregate_outcomes(checks: Iterable[Contract]) -> str:
    values = [check["outcome"] for check in checks]
    require(bool(values), "a normal RequirementReport needs at least one check")
    require(all(value in _PRECEDENCE for value in values), "invalid requirement outcome")
    return max(values, key=_PRECEDENCE.__getitem__)


def _check(*, code: str, category: str, outcome: str, reason_code: str,
           subject_refs: list[Contract], measurement: Contract | None = None,
           provenance: Contract | None = None) -> Contract:
    item: Contract = {"code": code, "category": category, "outcome": outcome,
                      "reason_code": reason_code, "subject_refs": deepcopy(subject_refs)}
    if measurement is not None:
        item["measurement"] = deepcopy(measurement)
    if provenance is not None:
        item["provenance"] = deepcopy(provenance)
    return item


def _mapped_outcome(rule: Contract, condition: str) -> str:
    outcomes = rule.get("outcomes")
    if not isinstance(outcomes, dict) or outcomes.get(condition) not in _PRECEDENCE:
        raise PolicyConfigurationError(f"rule outcome is not configured: {rule.get('code')}:{condition}")
    return outcomes[condition]


def _selected_rules(catalog: Contract, scope: str, record: Contract,
                    time_resolution: Contract) -> list[Contract]:
    if scope not in {"EVIDENCE", "FINAL_PACKAGE"}:
        raise PolicyConfigurationError(f"no matching catalog entry for scope: {scope}")
    report_type = record.get("event", {}).get("safety_report_type", {}).get("value")
    if report_type not in catalog["applies_to_report_types"]:
        raise PolicyConfigurationError(f"no matching catalog entry for report type: {report_type}")
    rules = deepcopy(catalog["scopes"][scope]["always"])
    if scope == "FINAL_PACKAGE":
        status = time_resolution.get("status")
        post_stamp = time_resolution.get("post_stamp")
        reason = post_stamp.get("reason_code") if isinstance(post_stamp, dict) else None
        if status not in {"OK", "NEEDS_REVIEW", "UNKNOWN"} or not isinstance(reason, str):
            raise PolicyConfigurationError("time display selector is malformed")
        cases = catalog["scopes"][scope]["conditional"][0]["cases"]
        selected = [case for case in cases if case.get("when") == {
            "status": status, "post_stamp_reason_code": reason}]
        if len(selected) != 1:
            raise PolicyConfigurationError("time display branch must select exactly one rule")
        if selected[0].get("no_rule") is not True:
            rules.append(deepcopy(selected[0]))
    codes = [rule["code"] for rule in rules]
    if not rules or len(codes) != len(set(codes)):
        raise PolicyConfigurationError("selected requirement rules must be non-empty and unique")
    unsupported = [code for code in codes if code not in _SUPPORTED_RULES]
    if unsupported:
        raise PolicyConfigurationError(f"unsupported requirement rule: {unsupported[0]}")
    return rules


def _plate_value(record: Contract) -> str | None:
    vehicle_number = record.get("vehicle_number")
    value = vehicle_number.get("value") if isinstance(vehicle_number, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def _plate_readout_performed(record: Contract) -> bool:
    """ADR-EVIDENCE-008 §5.1: a PlateReadout was an assembly input for this selection.

    Separates "read but not identified" (plate-less Package allowed) from an execution
    failure (`PlateReadout=None`), which must never reach a WARN Package.
    """
    return any(
        isinstance(ref, dict) and ref.get("kind") == "plate_readout"
        for ref in record.get("provenance", {}).get("input_refs", [])
    )


def _evidence_check(rule: Contract, record: Contract) -> Contract:
    code = rule["code"]
    subject = [deepcopy(record["record_ref"])]
    if code == "evidence.vehicle_number.present":
        if _plate_value(record) is not None:
            condition, reason = "value_present", "evidence.value_confirmed"
        elif _plate_readout_performed(record):
            condition, reason = "readout_performed_value_absent", "evidence.plate_unidentified"
        else:
            condition, reason = "readout_absent", "evidence.plate_readout_missing"
    elif code == "evidence.occurred_at.present":
        occurred = record.get("occurred_at")
        if not occurred:
            condition, reason = "occurred_at_absent", "evidence.time_unavailable"
        elif occurred.get("resolution_status") == "NEEDS_REVIEW":
            condition, reason = "resolution_status_needs_review", "evidence.time_needs_review"
        elif occurred.get("resolution_status") == "OK":
            condition, reason = "resolution_status_ok", "evidence.value_confirmed"
        else:
            raise PolicyConfigurationError("unregistered occurred_at resolution status")
    elif code == "evidence.visual_event.present":
        value = record.get("event", {}).get("visual_event_type", {}).get("value")
        response = record.get("situation_response", {}).get("value")
        if value is not None:
            condition, reason = "visual_event_type_present", "evidence.value_confirmed"
        elif response == "USER_UNSURE":
            condition, reason = "null_with_user_unsure", "evidence.visual_event_type_unconfirmed"
        else:
            condition, reason = "otherwise_unresolved", "evidence.visual_event_unresolved"
    elif code == "evidence.location.present":
        location = record.get("location") or {}
        has_value = any(isinstance(item, dict) and item.get("value") is not None for item in location.values())
        condition = "any_location_value" if has_value else "no_location_value"
        reason = "evidence.location_available" if has_value else "evidence.location_unavailable"
    else:
        raise PolicyConfigurationError(f"unsupported evidence rule: {code}")
    return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                  reason_code=reason, subject_refs=subject)


def _asset_ref_key(asset: Contract) -> tuple[str, str]:
    ref = asset.get("asset_ref")
    if not isinstance(ref, dict) or not isinstance(ref.get("kind"), str) or not isinstance(ref.get("ref"), str):
        raise PolicyConfigurationError("AssetFacts asset_ref is malformed")
    return ref["kind"], ref["ref"]


def _package_assets(asset_facts: Iterable[Contract]) -> list[Contract]:
    selected: dict[tuple[str, str], Contract] = {}
    for raw in asset_facts:
        if not isinstance(raw, dict):
            raise PolicyConfigurationError("AssetFacts entry must be an object")
        if raw.get("derived_role") not in _PACKAGE_ROLES:
            continue
        key = _asset_ref_key(raw)
        if key in selected and selected[key] != raw:
            raise PolicyConfigurationError(f"conflicting AssetFacts for {key[1]}")
        selected[key] = deepcopy(raw)
    return list(selected.values())


def _asset_by_role(asset_facts: Iterable[Contract], role: str) -> Contract | None:
    matches = [item for item in asset_facts if item.get("derived_role") == role]
    require(len(matches) <= 1, f"multiple AssetFacts entries for role {role}")
    return matches[0] if matches else None


def _observation_fact(facts: Contract, rule: Contract) -> Contract | None:
    name = rule.get("observation_fact")
    if not isinstance(name, str) or not name:
        raise PolicyConfigurationError(f"observation fact is not configured: {rule.get('code')}")
    value = facts.get(name)
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("value"), bool):
        raise PolicyConfigurationError(f"{name} must be a boolean observation fact")
    refs = value.get("subject_refs")
    if not isinstance(refs, list) or any(
        not isinstance(ref, dict) or not ref.get("kind") or not ref.get("ref") for ref in refs
    ):
        raise PolicyConfigurationError(f"{name}.subject_refs is malformed")
    return value


def _observation_check(rule: Contract, observation_facts: Contract) -> Contract:
    fact = _observation_fact(observation_facts, rule)
    condition = "not_observed" if fact is None else "observed_true" if fact["value"] else "observed_false"
    code = rule["code"]
    reason_roots = {
        "package.time.post_stamp_applied": "time.post_stamp",
    }
    suffix = {"observed_true": "confirmed", "observed_false": "failed",
              "not_observed": "not_observed"}[condition]
    overrides = rule.get("reason_codes") or {}
    return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                  reason_code=overrides.get(condition) or f"{reason_roots[code]}.{suffix}",
                  subject_refs=[] if fact is None else fact["subject_refs"])


def _location_snapshot(record: Contract) -> Contract | None:
    location = record.get("location") or {}
    display = next(
        (
            value
            for key in ("address", "place_name", "user_hint")
            if isinstance(location.get(key), dict)
            and isinstance(value := location[key].get("value"), str)
            and value.strip()
        ),
        None,
    )
    if display is None:
        return None
    result: Contract = {"display_text": display}
    keyword = location.get("search_keyword", {}).get("value")
    if isinstance(keyword, str) and keyword.strip():
        result["search_keyword"] = keyword
    return result


def _selected_template_ref(record: Contract) -> str | None:
    response = record.get("situation_response", {}).get("value")
    visual_type = record.get("event", {}).get("visual_event_type", {}).get("value")
    has_location = _location_snapshot(record) is not None
    has_plate = _plate_value(record) is not None
    if not has_plate and not _plate_readout_performed(record):
        return None
    if visual_type is not None and response in {"CONFIRMED", "CORRECTED"}:
        return {
            (True, True): SPECIFIC_TEMPLATE_REF,
            (False, True): SPECIFIC_NO_LOCATION_TEMPLATE_REF,
            (True, False): SPECIFIC_NO_PLATE_TEMPLATE_REF,
            (False, False): SPECIFIC_NO_LOCATION_NO_PLATE_TEMPLATE_REF,
        }[(has_location, has_plate)]
    if visual_type is None and response == "USER_UNSURE":
        return {
            (True, True): GENERIC_TEMPLATE_REF,
            (False, True): GENERIC_NO_LOCATION_TEMPLATE_REF,
            (True, False): GENERIC_NO_PLATE_TEMPLATE_REF,
            (False, False): GENERIC_NO_LOCATION_NO_PLATE_TEMPLATE_REF,
        }[(has_location, has_plate)]
    return None


def _render_from_record(record: Contract) -> Contract | None:
    occurred = record.get("occurred_at")
    template_ref = _selected_template_ref(record)
    if not isinstance(occurred, dict) or template_ref is None:
        return None
    event = record.get("event") or {}
    expression = event.get("violation_expression", {}).get("value")
    if not isinstance(expression, str) or not expression:
        return None
    location = _location_snapshot(record)
    return render_report(
        visual_event_type=event.get("visual_event_type", {}).get("value"),
        situation_response=record.get("situation_response", {}).get("value"),
        occurred_at=occurred.get("value"),
        location_display=None if location is None else location["display_text"],
        vehicle_number=_plate_value(record), violation_expression=expression)


def _render_inputs_complete(rule: Contract, record: Contract) -> bool:
    required_by_template = rule.get("render_required_inputs_by_template")
    if not isinstance(required_by_template, dict):
        raise PolicyConfigurationError("content-length template requirements are not configured")
    mode = "with_location" if _location_snapshot(record) is not None else "without_location"
    if _plate_value(record) is None:
        mode += "_without_plate"
    required = required_by_template.get(mode)
    allowed = {"occurred_at", "package_display_location", "vehicle_number",
               "plate_readout_performed", "violation_expression", "situation_response"}
    if not isinstance(required, list) or not required or any(item not in allowed for item in required):
        raise PolicyConfigurationError("content-length template requirements are malformed")
    if len(required) != len(set(required)):
        raise PolicyConfigurationError("content-length template requirements are duplicated")
    available = {
        "occurred_at": isinstance(record.get("occurred_at"), dict)
        and isinstance(record["occurred_at"].get("value"), str),
        "package_display_location": _location_snapshot(record) is not None,
        "vehicle_number": _plate_value(record) is not None,
        "plate_readout_performed": _plate_readout_performed(record),
        "violation_expression": bool(record.get("event", {}).get("violation_expression", {}).get("value")),
        "situation_response": record.get("situation_response", {}).get("value")
        in {"CONFIRMED", "CORRECTED", "USER_UNSURE"},
    }
    return all(available[item] for item in required)


def _attachment_check(rule: Contract, assets: list[Contract], policy: Contract) -> Contract:
    code = rule["code"]
    limits = policy["limits"]
    is_image, is_video = ".image." in code, ".video." in code
    relevant = [item for item in assets if (
        not is_image and not is_video
        or is_image and item.get("derived_role") == "PLATE_IMAGE"
        or is_video and item.get("derived_role") == "REPORT_VIDEO")]
    attachment_set_complete = any(item.get("derived_role") == "REPORT_VIDEO" for item in assets)
    sizes = [item.get("byte_size") for item in relevant]
    if any(value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ) for value in sizes):
        raise PolicyConfigurationError("AssetFacts byte_size is malformed")
    if code.endswith("each_size"):
        limit = limits["image_each_bytes" if is_image else "video_each_bytes"]
        known = [value for value in sizes if value is not None]
        actual = max(known, default=0)
        condition = ("exceeds_limit" if any(size > limit for size in known)
                     else "measurement_incomplete" if len(known) != len(relevant)
                     else "within_limit")
        reason = {"within_limit": "asset.size_within_policy", "exceeds_limit": "asset.size_exceeds_policy",
                  "measurement_incomplete": "asset.byte_size_unknown"}[condition]
        unit = policy["measurement_unit"]
    elif code.endswith("total_size"):
        limit = limits["total_bytes"]
        known = [value for value in sizes if value is not None]
        actual = sum(known)
        condition = ("exceeds_limit" if actual > limit else "measurement_incomplete"
                     if len(known) != len(relevant) or not attachment_set_complete else "within_limit")
        reason = {"within_limit": "asset.total_size_within_policy",
                  "exceeds_limit": "asset.total_size_exceeds_policy",
                  "measurement_incomplete": "asset.total_size_unknown"}[condition]
        unit = policy["measurement_unit"]
    else:
        limit = limits["image_count" if is_image else "video_count" if is_video else "total_count"]
        actual = len(relevant)
        condition = ("attachment_set_incomplete" if not attachment_set_complete
                     else "exceeds_limit" if actual > limit else "within_limit")
        reason = {"within_limit": "asset.count_within_policy", "exceeds_limit": "asset.count_exceeds_policy",
                  "attachment_set_incomplete": "asset.attachment_set_unknown"}[condition]
        unit = policy["count_unit"]
    return _check(code=code, category=rule["category"], outcome=policy["outcome_mapping"][condition],
                  reason_code=reason, subject_refs=[deepcopy(item["asset_ref"]) for item in relevant],
                  measurement={"actual": actual, "limit": limit, "unit": unit},
                  provenance={"policy_ref": policy["policy_ref"]})


def _final_check(rule: Contract, record: Contract, assets: list[Contract],
                 observation_facts: Contract, time_resolution: Contract, evaluated_at: str,
                 attachment_policy: Contract, deadline_policy: Contract) -> Contract:
    code = rule["code"]
    evidence_ref = deepcopy(record["record_ref"])
    if code == "package.asset.report_video.exists":
        report_videos = [item for item in assets if item.get("derived_role") == "REPORT_VIDEO"]
        if not report_videos:
            condition, reason, refs = "availability_unknown_or_fact_missing", "asset.fact_missing", []
        else:
            availabilities = [item.get("availability") for item in report_videos]
            if any(item not in {"AVAILABLE", "UNKNOWN", "UNAVAILABLE"} for item in availabilities):
                raise PolicyConfigurationError("AssetFacts availability is malformed")
            if any(item == "UNAVAILABLE" for item in availabilities):
                condition, reason = "unavailable", "asset.unavailable"
            elif any(item == "UNKNOWN" for item in availabilities):
                condition, reason = "availability_unknown_or_fact_missing", "asset.availability_unknown"
            else:
                condition, reason = "available", "asset.available"
            refs = [item["asset_ref"] for item in report_videos]
        return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                      reason_code=reason, subject_refs=refs)
    if rule.get("input") == "observation_fact":
        return _observation_check(rule, observation_facts)
    if code == "package.location.present":
        present = _location_snapshot(record) is not None
        condition = "display_location_present" if present else "display_location_absent"
        return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                      reason_code="package.location_available" if present else "package.location_unavailable",
                      subject_refs=[evidence_ref])
    if code == "package.report.content_length":
        rendered = _render_from_record(record) if _render_inputs_complete(rule, record) else None
        if rendered is None:
            return _check(code=code, category=rule["category"],
                          outcome=_mapped_outcome(rule, "render_inputs_incomplete"),
                          reason_code="report.inputs_incomplete", subject_refs=[evidence_ref])
        length = rendered["content_length"]
        condition = "rendered_within_range" if REPORT_TEXT_MIN_LENGTH <= length <= REPORT_TEXT_MAX_LENGTH else "rendered_outside_range"
        return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                      reason_code="report.content_length_valid" if condition == "rendered_within_range" else "report.content_length_invalid",
                      subject_refs=[evidence_ref],
                      measurement={"actual": length, "limit": REPORT_TEXT_MAX_LENGTH,
                                   "unit": rule["measurement_unit"]},
                      provenance={"template_ref": rendered["template_ref"],
                                  "policy_ref": SAFETY_REPORT_POLICY_REF})
    if code == "package.evidence.situation_response":
        response = record.get("situation_response", {}).get("value")
        condition = response if response in {"CONFIRMED", "CORRECTED", "USER_UNSURE"} else "NOT_ASKED_or_absent"
        reasons = {"CONFIRMED": "evidence.situation_confirmed", "CORRECTED": "evidence.situation_corrected",
                   "USER_UNSURE": "evidence.visual_event_type_unconfirmed",
                   "NOT_ASKED_or_absent": "evidence.situation_not_asked"}
        return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, condition),
                      reason_code=reasons[condition], subject_refs=[evidence_ref])
    if code.startswith("package.asset.") and code != "package.asset.report_video.exists":
        return _attachment_check(rule, assets, attachment_policy)
    if code == "package.deadline.within_policy":
        occurred = record.get("occurred_at")
        if occurred is None or time_resolution.get("status") == "UNKNOWN":
            return _check(code=code, category=rule["category"],
                          outcome=deadline_policy["outcome_mapping"]["OCCURRED_AT_MISSING"],
                          reason_code="deadline.occurred_at_missing", subject_refs=[evidence_ref],
                          provenance={"policy_ref": deadline_policy["policy_ref"],
                                      "calendar_ref": deadline_policy["calendar_ref"]})
        if occurred.get("time_resolution_ref") != time_resolution.get("resolution_ref"):
            raise PolicyConfigurationError("TimeResolution does not match EvidenceRecord.occurred_at")
        status = time_resolution.get("status")
        if status not in {"OK", "NEEDS_REVIEW"}:
            raise PolicyConfigurationError("deadline selector has an unregistered TimeResolution status")
        result = evaluate_deadline(occurred_at=occurred["value"], evaluated_at=evaluated_at,
                                   resolution_status=status, policy=deadline_policy)
        reason = (f"deadline.{result['deadline_status'].lower()}"
                  if result["condition"] == result["deadline_status"] else "deadline.time_needs_review")
        return _check(code=code, category=rule["category"],
                      outcome=deadline_policy["outcome_mapping"][result["condition"]],
                      reason_code=reason, subject_refs=[evidence_ref, deepcopy(time_resolution["resolution_ref"])],
                      measurement=result["measurement"],
                      provenance={**result["provenance"], "deadline_date": result["deadline_date"],
                                  "deadline_exclusive_at": result["deadline_exclusive_at"],
                                  "deadline_status": result["deadline_status"]})
    if code == "package.time.display_unresolved":
        return _check(code=code, category=rule["category"], outcome=_mapped_outcome(rule, "always"),
                      reason_code=rule["reason_code"],
                      subject_refs=[deepcopy(time_resolution["resolution_ref"])])
    raise PolicyConfigurationError(f"unsupported final-package rule: {code}")


def evaluate_requirements(evidence_record: Contract, *, scope: str, report_id: str,
                          evaluated_at: str, time_resolution: Contract,
                          asset_facts: Iterable[Contract] = (),
                          observation_facts: Contract | None = None,
                          supersedes_id: str | None = None) -> Contract:
    """Select the active catalog rules and evaluate them over contract values."""
    parse_rfc3339(evaluated_at)
    if not isinstance(time_resolution, dict):
        raise PolicyConfigurationError("TimeResolution is required for catalog selection")
    catalog = load_requirement_catalog()
    attachment_policy = load_attachment_policy()
    deadline_policy = load_deadline_policy()
    referenced = catalog.get("referenced_policies") or {}
    if referenced.get("attachment") != attachment_policy["policy_ref"]:
        raise PolicyConfigurationError("catalog attachment policy_ref is not registered")
    if (referenced.get("deadline") != deadline_policy["policy_ref"]
            or referenced.get("calendar") != deadline_policy["calendar_ref"]):
        raise PolicyConfigurationError("catalog deadline policy refs are not registered")
    if referenced.get("report_template") != SAFETY_REPORT_POLICY_REF:
        raise PolicyConfigurationError("catalog report template policy_ref is not registered")
    rules = _selected_rules(catalog, scope, evidence_record, time_resolution)
    assets = _package_assets(asset_facts)
    if scope == "EVIDENCE":
        checks = [_evidence_check(rule, evidence_record) for rule in rules]
    else:
        checks = [_final_check(rule, evidence_record, assets, observation_facts or {}, time_resolution,
                               evaluated_at, attachment_policy, deadline_policy) for rule in rules]
    report: Contract = {
        "contract_version": "requirement-report/v1",
        "requirement_report_ref": contract_ref("requirement_report", report_id),
        "scope": scope,
        "basis": {"evidence_record_ref": deepcopy(evidence_record["record_ref"]),
                  "asset_refs": [deepcopy(item["asset_ref"]) for item in assets]
                  if scope == "FINAL_PACKAGE" else []},
        "policy_ref": catalog["policy_ref"], "evaluated_at": evaluated_at,
        "overall": aggregate_outcomes(checks), "checks": checks,
    }
    if scope == "FINAL_PACKAGE" and (template_ref := _selected_template_ref(evidence_record)) is not None:
        report["basis"]["template_ref"] = template_ref
    if supersedes_id:
        report["supersedes_ref"] = contract_ref("requirement_report", supersedes_id)
    return report


def build_report_package(evidence_record: Contract, requirement_report: Contract, *,
                         package_id: str, created_at: str, asset_facts: Iterable[Contract],
                         assembly_succeeded: bool = True,
                         supersedes_id: str | None = None) -> Contract:
    """Build a ready-only immutable bundle or raise a stable boundary error."""
    parse_rfc3339(created_at)
    if (requirement_report.get("scope") != "FINAL_PACKAGE"
            or requirement_report.get("overall") not in {"PASS", "WARN"}):
        raise PackageNotReady("package.requirement_not_ready")
    if validate_requirement_report(requirement_report):
        raise PackageNotReady("package.requirement_report_invalid")
    if requirement_report.get("basis", {}).get("evidence_record_ref") != evidence_record.get("record_ref"):
        raise PackageNotReady("package.requirement_basis_mismatch")
    if not assembly_succeeded:
        raise PackageNotReady("package.assembly_failed")
    assets = _package_assets(asset_facts)
    evaluated_asset_refs = {
        (ref["kind"], ref["ref"])
        for ref in requirement_report["basis"]["asset_refs"]
    }
    package_asset_refs = {_asset_ref_key(asset) for asset in assets}
    report_video = _asset_by_role(assets, "REPORT_VIDEO")
    if report_video is None or report_video.get("availability") != "AVAILABLE":
        raise PackageNotReady("package.asset.report_video_missing")
    if report_video.get("byte_size") is None:
        raise PackageNotReady("package.asset.report_video_size_unknown")
    if not package_asset_refs.issubset(evaluated_asset_refs):
        raise PackageNotReady("package.requirement_asset_basis_mismatch")

    event = evidence_record["event"]
    visual_event_type = event["visual_event_type"]["value"]
    situation_response = evidence_record.get("situation_response", {}).get("value")
    if visual_event_type is None and situation_response != "USER_UNSURE":
        raise PackageNotReady("package.input.user_unsure_required")
    if visual_event_type is not None and situation_response not in {"CONFIRMED", "CORRECTED"}:
        raise PackageNotReady("package.input.situation_unconfirmed")
    occurred, plate = evidence_record.get("occurred_at"), _plate_value(evidence_record)
    if occurred is None:
        raise PackageNotReady("package.input.occurred_at_missing")
    # A plate-less Package exists only when the plate was read but not identified; an
    # execution failure (no PlateReadout) is not that result (ADR-EVIDENCE-008 §6).
    if plate is None and not _plate_readout_performed(evidence_record):
        raise PackageNotReady("package.input.vehicle_number_missing")
    location = _location_snapshot(evidence_record)
    rendered = render_report(visual_event_type=visual_event_type, situation_response=situation_response,
                             occurred_at=occurred["value"],
                             location_display=None if location is None else location["display_text"],
                             vehicle_number=plate,
                             violation_expression=event["violation_expression"]["value"])
    expected_template = requirement_report.get("basis", {}).get("template_ref")
    if expected_template and expected_template != rendered["template_ref"]:
        raise PackageNotReady("package.template_basis_mismatch")

    report_video_ref = deepcopy(report_video["asset_ref"])
    plate_image = _asset_by_role(assets, "PLATE_IMAGE")
    source_refs: list[Contract] = []
    for item in report_video.get("lineage") or []:
        if item.get("kind") in {"source_asset", "external_source"} and item not in source_refs:
            source_refs.append(deepcopy(item))
    derived_refs = [report_video_ref]
    package_assets: Contract = {"report_video_ref": report_video_ref}
    if plate_image and plate_image.get("availability") == "AVAILABLE":
        package_assets["plate_image_ref"] = deepcopy(plate_image["asset_ref"])
        derived_refs.append(deepcopy(plate_image["asset_ref"]))
    package: Contract = {
        "contract_version": "report-package/v1.2",
        "package_ref": contract_ref("report_package", package_id),
        "evidence_record_ref": deepcopy(evidence_record["record_ref"]),
        "requirement_report_ref": deepcopy(requirement_report["requirement_report_ref"]),
        "created_at": created_at,
        "report_inputs": {
            "safety_report_type": report_type_label(event["safety_report_type"]["value"]),
            "occurred_at": occurred["value"], "location": location,
            "vehicle_number": plate,
            "violation_expression": event["violation_expression"]["value"],
        },
        "report": {"title": rendered["title"], "description": rendered["description"],
                   "template_ref": rendered["template_ref"]},
        "assets": package_assets,
        "provenance": {"source_refs": source_refs, "derived_asset_refs": derived_refs,
                       "policy_ref": SAFETY_REPORT_POLICY_REF},
        "handoff": {"destination": "SAFETY_REPORT",
                    "supported_actions": ["DOWNLOAD_ASSETS", "COPY_FIELDS", "OPEN_DESTINATION"]},
    }
    if supersedes_id:
        package["supersedes_ref"] = contract_ref("report_package", supersedes_id)
    return package
