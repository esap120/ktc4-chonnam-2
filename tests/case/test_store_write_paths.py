"""진입점이 저장소를 load_for_update → save로 쓰는가 — 거부된 command는 저장하지 않는다(Review Focus 1)."""

from __future__ import annotations

from daesingo.case import command, service
from daesingo.case.domain import Candidate
from daesingo.case.store import CaseStore


def _store_with_two_candidates() -> tuple[CaseStore, str]:
    store = CaseStore()
    case_id = service.create_case(store=store)
    case = store.load_for_update(case_id)
    case.start_search()
    case.receive_candidates([
        Candidate(candidate_id="cand_a", at=None, at_provenance=None, observed="", thumb_ref=None, rank=1),
        Candidate(candidate_id="cand_b", at=None, at_provenance=None, observed="", thumb_ref=None, rank=2),
    ])
    case.select_candidate("cand_a")
    store.save(case)
    return store, case_id


class _NoDownstream:
    """선택 뒤 CaseView가 adapter를 조회하므로 downstream 값이 없는 adapter를 붙인다 — `ModuleAdapter` Protocol
    (`adapters.py`)의 조회 메서드를 전부 「없음」으로 답한다."""

    def get_candidate_events(self): return []
    def get_candidate_search_outcome(self): return None
    def get_analysis_scopes(self): return []
    def get_evidence_record(self): return None
    def get_evidence_records(self): return []
    def get_requirement_report(self, scope): return None
    def get_requirement_reports(self, scope): return []
    def get_evidence_needs(self): return []
    def get_report_package(self): return None
    def get_plate_readouts(self): return []
    def get_overlay_time_readouts(self): return []
    def get_plate_read_status(self): return None
    def get_visual_evidence_decision(self): return None
    def get_independent_facts(self): return None
    def get_job_executions(self): return []


def test_successful_command_is_persisted():
    store, case_id = _store_with_two_candidates()
    store.adapters.put(case_id, _NoDownstream())
    rev = store.get_case(case_id).case_rev
    result = command.execute_command(
        {"case_id": case_id, "expected_case_rev": rev, "kind": "SELECT_OTHER_CANDIDATE", "payload": {"candidate_id": "cand_b"}},
        store=store,
    )
    assert result.response["ok"] is True
    saved = store.get_case(case_id)
    assert [c.candidate_id for c in saved.candidates if c.selected] == ["cand_b"]
    assert saved.correction_records[-1]["kind"] == "OTHER_CANDIDATE"


def test_rejected_command_leaves_no_trace():
    store, case_id = _store_with_two_candidates()
    store.adapters.put(case_id, _NoDownstream())
    before = store.get_case(case_id)
    result = command.execute_command(
        {"case_id": case_id, "expected_case_rev": before.case_rev, "kind": "MARK_REVIEWED", "payload": {}},
        store=store,
    )
    assert result.response["ok"] is False
    assert store.get_case(case_id) == before


def test_record_source_registered_is_persisted():
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(case_id, {"source_asset_ref": "sa_1", "availability": "AVAILABLE"}, store=store)
    assert store.get_case(case_id).manifest_summary["file_count"] == 1
