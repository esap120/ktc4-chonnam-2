"""분석 시작 로직 — `decisions/start-analysis.md` §2 · §3."""

import pytest

from daesingo.case import analysis_start as a
from daesingo.case.domain import CaseAggregate, InvalidTransition
from daesingo.case.timeline_source import CaseTimeline, TimelineUnavailable

BUDGET = a.InitialSearchBudget()


class FakeTimelines:
    def __init__(self, duration_ms: int = 20_000, fail: bool = False):
        self.calls: list[list[dict]] = []
        self.duration_ms = duration_ms
        self.fail = fail

    def timeline_for(self, sources):
        self.calls.append(sources)
        if self.fail:
            raise TimelineUnavailable("fake")
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=self.duration_ms)


def _case(n_sources: int = 1) -> CaseAggregate:
    case = CaseAggregate.empty("case_as")
    for i in range(n_sources):
        case.record_source_registered(
            {"source_asset_ref": f"sa_{i}", "availability": "AVAILABLE", "duration_sec": 10.0},
            [{"media_stream_ref": f"ms_{i}", "media_type": "VIDEO"}],
        )
    return case


def _ok(**hints):
    return {"status": "OK", **{f"{k}_hint": v for k, v in hints.items()}}


def test_description_issues_hint_extract_only():
    case, timelines = _case(), FakeTimelines()
    a.start_analysis(case, "흰 SUV가 끼어들었어요", timelines=timelines, budget=BUDGET)
    assert case.stage == "SEARCHING"
    assert case.case_rev == 1
    assert case.description == "흰 SUV가 끼어들었어요"
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT"]
    assert case.job_records[0]["input_fingerprint"] == a.fingerprint(
        {"kind": "HINT_EXTRACT", "description": "흰 SUV가 끼어들었어요", "prior_hints": None}
    )
    assert timelines.calls == []


@pytest.mark.parametrize("description", ["", "   "])
def test_blank_description_issues_coarse_search_directly(description):
    case = _case()
    a.start_analysis(case, description, timelines=FakeTimelines(), budget=BUDGET)
    assert case.description == description
    assert [r["kind"] for r in case.job_records] == ["COARSE_SEARCH"]
    assert case.hints == {"time": None, "vehicle": None, "situation": None, "location": None}


def test_no_processable_source_is_not_allowed():
    case = _case(n_sources=0)
    with pytest.raises(a.AnalysisStartNotAllowed):
        a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    assert case.stage == "INTAKE"
    assert case.description is None


def test_second_start_is_rejected_by_stage():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    with pytest.raises(InvalidTransition):
        a.start_analysis(case, "y", timelines=FakeTimelines(), budget=BUDGET)
    assert case.description == "x"


def test_initial_search_scope_shape():
    case = _case(n_sources=2)
    timelines = FakeTimelines(duration_ms=20_000)
    a.start_analysis(case, "", timelines=timelines, budget=BUDGET)
    job = case.job_records[-1]
    scope = case.analysis_scopes[job["scope_ref"]]
    assert timelines.calls == [case.sources]
    assert scope["time_ranges"] == [
        {"kind": "TIMELINE_RELATIVE", "timeline_ref": {"timeline_id": "tl_1", "revision": 1}, "start_ms": 0, "end_ms": 20_000}
    ]
    assert scope["target_event_types"] == list(a.TARGET_EVENT_TYPES)
    assert scope["budget"] == {"max_cost_krw": 1000.0, "max_latency_sec": 150.0}
    assert job["input_fingerprint"] == a.fingerprint(
        {"kind": "COARSE_SEARCH", "scope": {k: v for k, v in scope.items() if k != "scope_id"}}
    )


def test_fingerprint_ignores_scope_id():
    first, second = _case(), _case()
    a.start_analysis(first, "", timelines=FakeTimelines(), budget=BUDGET)
    a.start_analysis(second, "", timelines=FakeTimelines(), budget=BUDGET)
    assert first.job_records[0]["scope_ref"] != second.job_records[0]["scope_ref"]
    assert first.job_records[0]["input_fingerprint"] == second.job_records[0]["input_fingerprint"]


def test_reflect_ok_fills_hints_settles_and_issues_coarse():
    case = _case()
    a.start_analysis(case, "흰 SUV", timelines=FakeTimelines(), budget=BUDGET)
    hint_job = case.job_records[0]
    assert a.reflect_hint_extraction(case, _ok(vehicle="흰 SUV", time=" "), timelines=FakeTimelines(), budget=BUDGET)
    assert case.hints == {"time": None, "vehicle": "흰 SUV", "situation": None, "location": None}
    assert case.settled_jobs[hint_job["job_id"]] == "REFLECTED"
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]
    scope = case.analysis_scopes[case.job_records[-1]["scope_ref"]]
    assert scope["hint"]["vehicle"] == "흰 SUV"
    assert case.case_rev == 1


@pytest.mark.parametrize("status", ["ABSTAINED", "FAILED"])
def test_reflect_abstained_or_failed_uses_empty_hints(status):
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    assert a.reflect_hint_extraction(case, {"status": status, "vehicle_hint": "무시"}, timelines=FakeTimelines(), budget=BUDGET)
    assert case.hints == {"time": None, "vehicle": None, "situation": None, "location": None}
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]


def test_duplicate_result_changes_nothing():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    a.reflect_hint_extraction(case, _ok(vehicle="v"), timelines=FakeTimelines(), budget=BUDGET)
    before = (dict(case.hints), len(case.job_records))
    assert a.reflect_hint_extraction(case, _ok(vehicle="다른 값"), timelines=FakeTimelines(), budget=BUDGET) is False
    assert (case.hints, len(case.job_records)) == before


def test_unknown_status_raises_before_any_change():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    with pytest.raises(ValueError):
        a.reflect_hint_extraction(case, {"status": "WHAT"}, timelines=FakeTimelines(), budget=BUDGET)
    assert case.settled_jobs == {}
    assert len(case.job_records) == 1


def test_timeline_failure_propagates():
    case = _case()
    with pytest.raises(TimelineUnavailable):
        a.start_analysis(case, "", timelines=FakeTimelines(fail=True), budget=BUDGET)
