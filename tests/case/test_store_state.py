"""aggregate ↔ 저장 형식 직렬화 — `decisions/case-store-mysql.md` §4."""

from __future__ import annotations

import copy

import pytest

from daesingo.case import jobs
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store_state import STATE_VERSION, StateVersionTooNew, from_row, to_row


def _case() -> CaseAggregate:
    case = CaseAggregate.empty("case_state001")
    case.start_search()
    scope = {"scope_id": "s1", "time_ranges": [], "target_event_types": [], "hint": {}, "budget": {}, "contract_version": "x"}
    jobs.issue_coarse_search(case, scope_ref="s1", input_fingerprint="sha1:c", scope=scope)
    case.receive_candidates([Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="o", thumb_ref="fr_1", rank=1)])
    case.select_candidate("cand_a")
    return case


def test_round_trip_keeps_every_field():
    case = _case()
    back = from_row(to_row(case))
    assert back == case
    assert back.candidates[0].thumb_ref == "fr_1"
    assert back.analysis_scopes["s1"]["scope_id"] == "s1"


def test_row_splits_columns_records_and_state():
    row = to_row(_case())
    assert (row.case_id, row.stage, row.selection_rev) == ("case_state001", "EVIDENCE_REVIEW", 1)
    assert row.state["state_version"] == STATE_VERSION
    assert "job_records" not in row.state and "analysis_scopes" not in row.state
    assert [r["kind"] for r in row.job_records] == ["COARSE_SEARCH"]


def test_unknown_state_keys_survive_round_trip():
    row = to_row(_case())
    state = copy.deepcopy(row.state)
    state["future_field"] = {"x": 1}
    state["candidates"][0]["future_candidate_field"] = "y"
    back = from_row(type(row)(**{**row.__dict__, "state": state}))
    again = to_row(back)
    assert again.state["future_field"] == {"x": 1}
    assert again.state["candidates"][0]["future_candidate_field"] == "y"


def test_missing_state_key_takes_default():
    row = to_row(_case())
    state = {k: v for k, v in row.state.items() if k != "candidate_generation"}
    back = from_row(type(row)(**{**row.__dict__, "state": state}))
    assert back.candidate_generation == 0


def test_newer_state_version_is_refused():
    row = to_row(_case())
    state = {**row.state, "state_version": STATE_VERSION + 1}
    with pytest.raises(StateVersionTooNew):
        from_row(type(row)(**{**row.__dict__, "state": state}))


def test_scope_is_immutable_per_id():
    case = _case()
    with pytest.raises(ValueError):
        case.record_analysis_scope({"scope_id": "s1", "time_ranges": ["changed"]})


@pytest.mark.parametrize("bad", ["", "s" * 129, "스코프"])
def test_record_analysis_scope_rejects_bad_scope_id(bad):
    case = CaseAggregate.empty("case_scope001")
    with pytest.raises(ValueError):
        case.record_analysis_scope({"scope_id": bad})
