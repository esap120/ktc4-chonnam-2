"""Load and validate immutable evidence policy data."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from .errors import PolicyConfigurationError

Contract = dict[str, Any]
_POLICY_DIR = Path(__file__).parent
_ACTIVE_REQUIREMENT_CATALOG_FILE = "requirement_rules_v6.json"
_CATEGORIES = {"EVIDENCE", "TIME", "VEHICLE", "LOCATION", "ASSET", "DEADLINE", "REPORT_CONTENT"}
_OUTCOMES = {"PASS", "WARN", "BLOCK", "UNKNOWN"}


def _fail(message: str) -> None:
    raise PolicyConfigurationError(message)


def _read_json(filename: str) -> Contract:
    try:
        value = json.loads((_POLICY_DIR / filename).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyConfigurationError(f"cannot load policy data: {filename}") from exc
    if not isinstance(value, dict):
        _fail(f"policy data must be an object: {filename}")
    return value


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_attachment_policy(value: Contract) -> Contract:
    if value.get("policy_ref") != "policy/safety-report-attachment-size/v1":
        _fail("invalid attachment policy_ref")
    if value.get("measurement_unit") != "asset.bytes" or value.get("count_unit") != "asset.count":
        _fail("invalid attachment policy units")
    limits = value.get("limits")
    required_limits = {
        "image_each_bytes",
        "video_each_bytes",
        "total_bytes",
        "image_count",
        "video_count",
        "total_count",
    }
    if not isinstance(limits, dict) or set(limits) != required_limits:
        _fail("attachment policy limits are incomplete")
    if any(not _positive_int(limits[name]) for name in required_limits):
        _fail("attachment policy limits must be positive integers")
    outcomes = value.get("outcome_mapping")
    expected = {
        "within_limit": "PASS",
        "exceeds_limit": "BLOCK",
        "measurement_incomplete": "UNKNOWN",
        "attachment_set_incomplete": "UNKNOWN",
    }
    if outcomes != expected:
        _fail("invalid attachment outcome mapping")
    return deepcopy(value)


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        _fail(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PolicyConfigurationError(f"{field} must be an ISO date") from exc


def validate_deadline_policy(value: Contract) -> Contract:
    if value.get("policy_ref") != "policy/safety-report-deadline/v1":
        _fail("invalid deadline policy_ref")
    if value.get("calendar_ref") != "calendar/kr-public-holidays/2026-2027/r1":
        _fail("invalid deadline calendar_ref")
    if value.get("timezone") != "Asia/Seoul" or value.get("automatic_updates") is not False:
        _fail("invalid deadline timezone or update mode")
    start = _parse_date(value.get("coverage_start"), "coverage_start")
    end = _parse_date(value.get("coverage_end"), "coverage_end")
    if start > end:
        _fail("deadline coverage is reversed")
    rule = value.get("deadline_rule")
    expected_rule = {
        "duration": 2,
        "unit": "CALENDAR_DAY",
        "exclude_incident_date": True,
        "weekend_days": ["SATURDAY", "SUNDAY"],
        "last_day_extension": "NEXT_NON_WEEKEND_OR_HOLIDAY_DATE",
        "deadline_inclusive": "END_OF_LOCAL_DAY",
        "exclusive_upper_bound": "NEXT_DAY_START",
    }
    if rule != expected_rule:
        _fail("invalid deadline rule configuration")
    expected_outcomes = {
        "OPEN": "PASS",
        "EXTENDED": "PASS",
        "EXCEEDED": "WARN",
        "OCCURRED_AT_MISSING": "UNKNOWN",
        "TIME_RESOLUTION_NEEDS_REVIEW": "WARN",
    }
    if value.get("outcome_mapping") != expected_outcomes:
        _fail("invalid deadline outcome mapping")

    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        _fail("deadline sources are required")
    source_ids = [item.get("source_id") for item in sources if isinstance(item, dict)]
    if len(source_ids) != len(sources) or any(not isinstance(item, str) or not item for item in source_ids):
        _fail("deadline source_id is invalid")
    if len(source_ids) != len(set(source_ids)):
        _fail("deadline source_id values must be unique")

    holidays = value.get("holidays")
    expected_years = {str(year) for year in range(start.year, end.year + 1)}
    if not isinstance(holidays, dict) or set(holidays) != expected_years:
        _fail("deadline holiday coverage is incomplete")
    all_dates: list[date] = []
    for year in sorted(expected_years):
        entries = holidays[year]
        if not isinstance(entries, list) or not entries:
            _fail(f"deadline holiday snapshot is empty for {year}")
        year_dates: list[date] = []
        for item in entries:
            if not isinstance(item, dict):
                _fail("deadline holiday entry must be an object")
            holiday = _parse_date(item.get("date"), "holiday.date")
            if holiday.year != int(year) or not start <= holiday <= end:
                _fail("deadline holiday date is outside declared coverage")
            refs = item.get("source_ids")
            if not isinstance(refs, list) or not refs or any(ref not in source_ids for ref in refs):
                _fail("deadline holiday source_ids are invalid")
            year_dates.append(holiday)
        if year_dates != sorted(year_dates) or len(year_dates) != len(set(year_dates)):
            _fail(f"deadline holiday dates must be sorted and unique for {year}")
        all_dates.extend(year_dates)
    if len(all_dates) != len(set(all_dates)):
        _fail("deadline holiday dates must be globally unique")
    return deepcopy(value)


def validate_requirement_catalog(value: Contract) -> Contract:
    policy_ref = value.get("policy_ref")
    if not isinstance(policy_ref, str) or not policy_ref.startswith("policy/requirement-rules-v"):
        _fail("unknown requirement catalog policy_ref")
    if value.get("applies_to_report_types") != ["TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION"]:
        _fail("requirement catalog report types are invalid")
    referenced = value.get("referenced_policies")
    expected_refs = {"attachment", "deadline", "calendar", "report_template"}
    if (not isinstance(referenced, dict) or set(referenced) != expected_refs
            or any(not isinstance(item, str) or not item for item in referenced.values())):
        _fail("requirement catalog policy references are invalid")
    scopes = value.get("scopes")
    if not isinstance(scopes, dict) or set(scopes) != {"EVIDENCE", "FINAL_PACKAGE"}:
        _fail("requirement catalog scopes are invalid")
    all_codes: list[str] = []
    for scope, expected_count in (("EVIDENCE", 4), ("FINAL_PACKAGE", 11)):
        entry = scopes[scope]
        rules = entry.get("always") if isinstance(entry, dict) else None
        if not isinstance(rules, list) or len(rules) != expected_count:
            _fail(f"{scope} requirement catalog rule count is invalid")
        codes = [rule.get("code") for rule in rules if isinstance(rule, dict)]
        if len(codes) != len(rules) or any(not isinstance(code, str) or not code for code in codes):
            _fail(f"{scope} requirement catalog code is invalid")
        if len(codes) != len(set(codes)):
            _fail(f"{scope} requirement catalog codes must be unique")
        for rule in rules:
            if rule.get("category") not in _CATEGORIES:
                _fail(f"{scope} requirement catalog category is invalid")
            outcomes = rule.get("outcomes")
            policy_source = rule.get("policy_source")
            if outcomes is None and not isinstance(policy_source, str):
                _fail(f"{scope} requirement catalog outcomes are missing")
            if outcomes is not None and (
                not isinstance(outcomes, dict)
                or not outcomes
                or any(outcome not in _OUTCOMES for outcome in outcomes.values())
            ):
                _fail(f"{scope} requirement catalog outcomes are invalid")
        all_codes.extend(codes)
    conditional = scopes["FINAL_PACKAGE"].get("conditional")
    if not isinstance(conditional, list) or len(conditional) != 1:
        _fail("time display catalog branch must occur exactly once")
    branch = conditional[0]
    cases = branch.get("cases") if isinstance(branch, dict) else None
    if not isinstance(cases, list) or len(cases) != 4:
        _fail("time display catalog cases are invalid")
    if any(not isinstance(case, dict) for case in cases):
        _fail("time display rule code is invalid")
    for case in cases:
        # A no_rule branch is still selected by the time selector but adds no check (ADR-EVIDENCE-010).
        if case.get("no_rule") is True:
            if any(key in case for key in ("code", "category", "outcomes")):
                _fail("time display no_rule branch must not carry a rule")
            continue
        if not isinstance(case.get("code"), str):
            _fail("time display rule code is invalid")
        if case.get("category") != "TIME":
            _fail("time display rule category is invalid")
        outcomes = case.get("outcomes")
        if (not isinstance(outcomes, dict) or not outcomes
                or any(outcome not in _OUTCOMES for outcome in outcomes.values())):
            _fail("time display rule outcomes are invalid")
    selector = branch.get("selector")
    if not isinstance(selector, dict) or selector.get("exactly_one_required") is not True:
        _fail("time display selector must require exactly one rule")
    return deepcopy(value)


_REPORT_TEMPLATES_V1_1 = {
    "specific_template_ref": "tmpl/safety-report-specific-v1",
    "generic_template_ref": "tmpl/safety-report-generic-v1",
    "specific_no_location_template_ref": "tmpl/safety-report-specific-no-location-v1",
    "generic_no_location_template_ref": "tmpl/safety-report-generic-no-location-v1",
}
# v1.2 adds the no-plate variants (ADR-EVIDENCE-008 §6); v1.1 stays loadable for its history.
_REPORT_POLICY_REVISIONS = {
    "safety-report-policy/v1.1": ("safety-report-policy/v1", _REPORT_TEMPLATES_V1_1, ()),
    "safety-report-policy/v1.2": ("safety-report-policy/v1.1", {
        **_REPORT_TEMPLATES_V1_1,
        "specific_no_plate_template_ref": "tmpl/safety-report-specific-no-plate-v1",
        "generic_no_plate_template_ref": "tmpl/safety-report-generic-no-plate-v1",
        "specific_no_location_no_plate_template_ref": "tmpl/safety-report-specific-no-location-no-plate-v1",
        "generic_no_location_no_plate_template_ref": "tmpl/safety-report-generic-no-location-no-plate-v1",
    }, ("no_plate_notice",)),
}


def validate_report_policy(value: Contract) -> Contract:
    revision = _REPORT_POLICY_REVISIONS.get(value.get("policy_ref"))
    if revision is None:
        _fail("invalid report policy_ref")
    supersedes, expected_templates, extra_text = revision
    if value.get("supersedes_policy_ref") != supersedes:
        _fail("invalid superseded report policy_ref")
    if any(value.get(key) != expected for key, expected in expected_templates.items()):
        _fail("invalid report template registry")
    minimum = value.get("report_text_min_length")
    maximum = value.get("report_text_max_length")
    if not _positive_int(minimum) or not _positive_int(maximum) or minimum > maximum:
        _fail("invalid report text length policy")
    labels = value.get("report_type_labels")
    if not isinstance(labels, dict) or set(labels) != {"TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION"}:
        _fail("invalid report type labels")
    events = value.get("events")
    expected_events = {
        "SIGNAL", "CENTER_LINE_CROSSING", "SOLID_LINE_LANE_CHANGE",
        "MOTORCYCLE_HELMET_NON_USE",
    }
    if not isinstance(events, dict) or set(events) != expected_events:
        _fail("invalid report event registry")
    required_text = {
        "generic_title", "generic_violation_expression", "generic_description_tail",
        "specific_description_tail", *extra_text,
    }
    if any(not isinstance(value.get(key), str) or not value[key] for key in required_text):
        _fail("invalid report template text")
    for event in events.values():
        if (not isinstance(event, dict)
                or event.get("safety_report_type") not in labels
                or any(not isinstance(event.get(key), str) or not event[key]
                       for key in ("violation_expression", "title"))):
            _fail("invalid report event mapping")
    return deepcopy(value)


def load_attachment_policy() -> Contract:
    return validate_attachment_policy(_read_json("attachment_policy_v1.json"))


def load_deadline_policy() -> Contract:
    return validate_deadline_policy(_read_json("deadline_policy_v1.json"))


def load_requirement_catalog() -> Contract:
    return validate_requirement_catalog(_read_json(_ACTIVE_REQUIREMENT_CATALOG_FILE))


def load_report_policy() -> Contract:
    return validate_report_policy(_read_json("safety_report_policy_v1_2.json"))
