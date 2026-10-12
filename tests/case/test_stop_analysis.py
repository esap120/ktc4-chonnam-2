"""분석 중단(`STOP_ANALYSIS`) · 늦은 결과 guard — 고도화 8-9, `decisions/stop-analysis.md`.

중단은 `SEARCHING`에서 기다리던 `HINT_EXTRACT` · `COARSE_SEARCH`를 `CANCELLED`로 정산하고, composition root가 같은
transaction에서 Runtime cancel을 부르도록 그 `job_id`를 돌려준다(#245 C-1 · C-1a B, #292). 중단된 job의 결과는
반영하지 않는다(C-4).
"""
from __future__ import annotations

import pytest

from daesingo.case import command, jobs, service
from daesingo.case.domain import Candidate, CaseAggregate, InvalidTransition
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline

STOPPED = "case.analysis_stopped"


class FakeTimelines:
    def timeline_for(self, sources):
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


def _store_with_source() -> tuple[CaseStore, str]:
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(
        case_id,
        {"source_asset_ref": "sa_0", "availability": "AVAILABLE", "duration_sec": 10.0},
        media_streams=[{"media_stream_ref": "ms_0", "media_type": "VIDEO"}],
        store=store,
    )
    return store, case_id


def _req(case_id: str, kind: str, payload: dict, rev: int) -> dict:
    return {"case_id": case_id, "expected_case_rev": rev, "kind": kind, "payload": payload}


def _stop(case_id: str, rev: int) -> dict:
    return _req(case_id, "STOP_ANALYSIS", {}, rev)


def _searching(store: CaseStore, case_id: str, description: str = "") -> CaseAggregate:
    """빈 설명이면 바로 COARSE_SEARCH, 아니면 HINT_EXTRACT를 기다린다(`decisions/start-analysis.md`)."""
    result = command.execute_command(
        _req(case_id, "START_ANALYSIS", {"description": description}, 1), store=store, timelines=FakeTimelines()
    )
    assert result.response["ok"] is True
    return store.get_case(case_id)


def _codes(view: dict) -> list[str]:
    return [n["code"] for n in view["notices"]]


def _notice(view: dict, code: str) -> dict:
    return next(n for n in view["notices"] if n["code"] == code)


def _coarse_state(view: dict) -> str:
    return next(s["state"] for s in view["progress"] if s["step"] == "coarse_search")


# ── command ────────────────────────────────────────────────────────────────


def test_stop_cancels_waiting_search_and_returns_ids():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    coarse = jobs.latest_job_record(case, "COARSE_SEARCH")

    result = command.execute_command(_stop(case_id, case.case_rev), store=store)

    assert result.response["ok"] is True
    assert result.cancelled_job_ids == [coarse["job_id"]]
    assert result.appended_job_records == []
    after = store.get_case(case_id)
    assert after.settled_jobs[coarse["job_id"]] == "CANCELLED"
    assert after.case_rev == case.case_rev + 1
    assert after.stage == "SEARCHING"


def test_stop_during_hint_extraction_cancels_hint_job():
    store, case_id = _store_with_source()
    case = _searching(store, case_id, "흰 SUV")
    hint = jobs.latest_job_record(case, "HINT_EXTRACT")

    result = command.execute_command(_stop(case_id, case.case_rev), store=store)

    assert result.cancelled_job_ids == [hint["job_id"]]


def test_stop_leaves_other_kinds_alone():
    """지정한 탐색 job만 무효화한다 — 같은 case의 다른 kind job은 계속 기다린다(#245 C-1a B)."""
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    other = jobs.issue_job(case, "PLATE_IMAGE_EXPORT", input_fingerprint="f")
    store.save(case)

    result = command.execute_command(_stop(case_id, case.case_rev), store=store)

    assert other["job_id"] not in result.cancelled_job_ids
    assert other["job_id"] not in store.get_case(case_id).settled_jobs


def test_stop_without_waiting_search_is_not_allowed():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    command.execute_command(_stop(case_id, case.case_rev), store=store)

    again = command.execute_command(_stop(case_id, case.case_rev + 1), store=store)

    assert again.response["error"]["code"] == "case.command.not_allowed"
    assert again.cancelled_job_ids == []


def test_stop_outside_searching_is_not_allowed():
    """「초안 준비 중」 중단은 product 미결이라 받지 않는다(`decisions/stop-analysis.md`)."""
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    case.receive_candidates([_cand()])
    store.save(case)

    result = command.execute_command(_stop(case_id, case.case_rev), store=store)

    assert result.response["error"]["code"] == "case.command.not_allowed"


def test_stop_with_payload_keys_is_invalid():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)

    result = command.execute_command(_req(case_id, "STOP_ANALYSIS", {"x": "y"}, case.case_rev), store=store)

    assert result.response["error"]["code"] == "case.command.invalid_payload"


def test_stop_on_stale_revision_changes_nothing():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)

    result = command.execute_command(_stop(case_id, case.case_rev + 5), store=store)

    assert result.response["error"]["code"] == "case.command.stale_revision"
    assert result.cancelled_job_ids == []
    assert store.get_case(case_id).settled_jobs == case.settled_jobs


# ── view ───────────────────────────────────────────────────────────────────


def test_stopped_search_projects_partial_and_notice_with_resume():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)

    view = command.execute_command(_stop(case_id, case.case_rev), store=store).response["case_view"]

    assert view["running_jobs"] == []
    assert _coarse_state(view) == "PARTIAL"
    assert _notice(view, STOPPED) == {
        "code": STOPPED,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice.analysis_stopped",
        "actions": ["RETRY_SEARCH"],
    }


def test_stopped_before_any_search_has_no_resume_action():
    """단서 구조화 중 중단 — 다시 낼 `COARSE_SEARCH` 근거가 없어 action을 싣지 않는다."""
    store, case_id = _store_with_source()
    case = _searching(store, case_id, "흰 SUV")

    view = command.execute_command(_stop(case_id, case.case_rev), store=store).response["case_view"]

    assert _notice(view, STOPPED)["actions"] == []


def test_resume_clears_stopped_notice():
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    command.execute_command(_stop(case_id, case.case_rev), store=store)

    resumed = command.execute_command(
        _req(case_id, "RUN_NOTICE_ACTION", {"notice_code": STOPPED, "action": "RETRY_SEARCH"}, case.case_rev + 1),
        store=store,
    )

    view = resumed.response["case_view"]
    assert resumed.response["ok"] is True
    assert [r["kind"] for r in resumed.appended_job_records] == ["COARSE_SEARCH"]
    assert STOPPED not in _codes(view)
    assert _coarse_state(view) == "RUNNING"


def test_stopped_wins_over_earlier_search_failure():
    """실패 → 다시 찾기 → 중단이면 마지막 사용자 행동(중단)을 보인다."""
    store, case_id = _store_with_source()
    case = _searching(store, case_id)
    case.record_candidate_search_failure()
    scope_ref = jobs.latest_job_record(case, "COARSE_SEARCH")["scope_ref"]
    jobs.issue_coarse_search(case, scope_ref=scope_ref, input_fingerprint="f2")
    store.save(case)

    view = command.execute_command(_stop(case_id, case.case_rev), store=store).response["case_view"]

    assert _coarse_state(view) == "PARTIAL"
    assert "search.candidate_search_failed" not in _codes(view)
    assert STOPPED in _codes(view)


# ── 늦은 결과 guard ────────────────────────────────────────────────────────


def test_late_hint_result_of_cancelled_job_is_ignored():
    store, case_id = _store_with_source()
    case = _searching(store, case_id, "흰 SUV")
    hint = jobs.latest_job_record(case, "HINT_EXTRACT")
    command.execute_command(_stop(case_id, case.case_rev), store=store)

    result = service.receive_hint_extraction_result(
        case_id, {"status": "OK", "vehicle_hint": "흰 SUV"}, job_id=hint["job_id"], store=store, timelines=FakeTimelines()
    )

    assert result.reflected is False
    assert result.appended_job_records == []
    after = store.get_case(case_id)
    assert after.settled_jobs[hint["job_id"]] == "CANCELLED"
    assert jobs.latest_job_record(after, "COARSE_SEARCH") is None


def test_hint_result_settles_only_its_job():
    store, case_id = _store_with_source()
    case = _searching(store, case_id, "흰 SUV")
    hint = jobs.latest_job_record(case, "HINT_EXTRACT")

    result = service.receive_hint_extraction_result(
        case_id, {"status": "OK"}, job_id=hint["job_id"], store=store, timelines=FakeTimelines()
    )

    assert result.reflected is True
    assert store.get_case(case_id).settled_jobs[hint["job_id"]] == "REFLECTED"


def _case_waiting_coarse() -> tuple[CaseAggregate, dict]:
    case = CaseAggregate.intake(case_id="case_guard", hints={}, manifest_summary={})
    case.start_search()
    return case, jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f")


def _cand() -> Candidate:
    return Candidate(candidate_id="c1", at=None, at_provenance=None, observed="x", thumb_ref="t", rank=1)


def test_candidates_of_cancelled_job_are_ignored():
    case, coarse = _case_waiting_coarse()
    case.stop_analysis()

    assert case.receive_candidates([_cand()], job_id=coarse["job_id"]) is False
    assert case.stage == "SEARCHING"
    assert case.candidates == []


def test_search_failure_of_cancelled_job_is_ignored():
    case, coarse = _case_waiting_coarse()
    case.stop_analysis()

    assert case.record_candidate_search_failure(job_id=coarse["job_id"]) is False
    assert case.candidate_search_failed is False


def test_candidates_of_superseded_job_are_ignored():
    """대표 job은 가장 나중 job — 대체된 job의 늦은 결과는 반영하지 않는다(A§10-7)."""
    case, old = _case_waiting_coarse()
    new = jobs.issue_coarse_search(case, scope_ref="s", input_fingerprint="f2")

    assert case.receive_candidates([_cand()], job_id=old["job_id"]) is False
    assert case.receive_candidates([_cand()], job_id=new["job_id"]) is True
    assert case.settled_jobs[new["job_id"]] == "REFLECTED"


def test_unknown_job_id_is_a_programming_error():
    case, _ = _case_waiting_coarse()
    with pytest.raises(ValueError):
        case.receive_candidates([_cand()], job_id="job_not_mine")


def test_domain_stop_requires_waiting_search():
    case = CaseAggregate.intake(case_id="case_nostop", hints={}, manifest_summary={})
    case.start_search()
    with pytest.raises(InvalidTransition):
        case.stop_analysis()
