"""real 경로 재판독 — `PLATE_REREAD` Need로 발주된 `PLATE_READ`(force_rerun)를 `readout-native-hires`로 다시 읽는다
(`decisions/real-e2e-scenarios.md` §4-3, readout 계약 §3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from daesingo.case import correction, jobs, real_e2e, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import Candidate, CaseAggregate

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"


def _plate_reread_case():
    mock = MockFixtureAdapter(MOCK_ROOT, "plate_reread_001")
    scope = mock.get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_p001_real", hints=mock.get_hints(), manifest_summary={})
    real = RealAdapter(
        case_id="case_p001_real",
        case=case,
        search_scope=scope,
        mock_root=MOCK_ROOT,
        scenario_id="scenario_plate_reread_001",
    )
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref=scope["scope_id"], input_fingerprint="f")
    candidates = service.receive_search_candidates(case, real)
    case.select_candidate(candidates[0].candidate_id)
    jobs.issue_plate_read(case, input_fingerprint="sha1:p001-plate")
    return case, real


def _plate(view):
    return (view["evidence"]["plate_display"] or {}).get("value")


def _reread(case, real):
    needs = real.get_evidence_needs()[0]
    assert [i["kind"] for i in needs["items"]] == ["PLATE_REREAD"]
    jobs.issue_needed_jobs(case, needs)


def _add_second_candidate(case, real) -> str:
    """fixture 후보가 하나뿐이라, 같은 span의 두 번째 후보를 만든다 — 판독 fixture는 clip으로 찾으므로 B도 같은 clip을 읽는다."""
    a = next(c for c in case.candidates if c.selected)
    real._candidates_by_id["cand_b"] = real._candidates_by_id[a.candidate_id].model_copy(update={"candidate_id": "cand_b"})
    case.candidates.append(
        Candidate(candidate_id="cand_b", at=a.at, at_provenance=a.at_provenance, observed=a.observed, thumb_ref=a.thumb_ref, rank=2)
    )
    return a.candidate_id


@pytest.fixture
def profiles(monkeypatch):
    calls: list[tuple[str, str]] = []
    original = real_e2e.observe_fixture_candidate

    def spy(**kwargs):
        candidate = kwargs["candidate"]
        calls.append((candidate.candidate_id, kwargs.get("plate_source_profile", "readout-native")))
        if candidate.candidate_id == "cand_b":
            # 만든 후보라 search fixture의 VisualEvidence와 맞지 않는다 — 판독 프로파일 판단만 보고 관찰은 A 것으로 채운다.
            kwargs["candidate"] = candidate.model_copy(update={"candidate_id": "candidate_p001"})
        return original(**kwargs)

    monkeypatch.setattr(real_e2e, "observe_fixture_candidate", spy)
    return calls


def test_reread_job_reads_hires_and_clears_need():
    case, real = _plate_reread_case()
    assert _plate(service.build_view_from_adapter(case, real)) is None

    _reread(case, real)
    view = service.build_view_from_adapter(case, real)

    assert _plate(view) == "17나2867"
    assert real.get_evidence_needs()[0]["items"] == []


def test_reread_belongs_to_issuing_candidate(profiles):
    """A에서 낸 재판독은 A의 것 — B로 바꾸면 B는 native로 읽고, 돌아온 A는 다시 읽지 않는다(A→B→A 재사용)."""
    case, real = _plate_reread_case()
    a = _add_second_candidate(case, real)
    service.build_view_from_adapter(case, real)
    _reread(case, real)
    service.build_view_from_adapter(case, real)

    correction.reselect_candidate(case, "cand_b")
    service.build_view_from_adapter(case, real)
    correction.reselect_candidate(case, a)
    view = service.build_view_from_adapter(case, real)

    assert profiles == [(a, "readout-native"), (a, "readout-native-hires"), ("cand_b", "readout-native")]
    assert _plate(view) == "17나2867"


def test_new_generation_forgets_rereads(profiles):
    """재탐색으로 후보 목록이 바뀌면 재판독 수도 버린다 — 같은 후보도 native부터 다시 읽는다."""
    case, real = _plate_reread_case()
    a = next(c.candidate_id for c in case.candidates if c.selected)
    service.build_view_from_adapter(case, real)
    _reread(case, real)
    service.build_view_from_adapter(case, real)

    case.candidate_generation += 1
    case.bump_revision()
    service.build_view_from_adapter(case, real)

    assert profiles[-1] == (a, "readout-native")
