"""web → case 공용 command 진입점(`case.handle_command`) — `contract-case-command.md`(Draft v0).

요청 `{case_id, expected_case_rev, kind, payload}` → 응답 `{ok, error, case_view}`.
성공·실패 모두 그 시점의 CaseView를 싣고(§4), 실패하면 아무 상태도 바뀌지 않는다(§6).
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from daesingo import case as case_package
from daesingo.case import command, jobs, service
from daesingo.case.adapters import MockFixtureAdapter, RealAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import CaseStore

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
CASE_ID = "case_cmd001"

PLATE_READ_FAILED = {
    "code": "readout.plate_read_failed",
    "severity": "WARN",
    "blocking": False,
    "message_key": "notice.plate_read_failed",
    "actions": ["RETRY_PLATE_READ"],
}


class _NoPackageAdapter(MockFixtureAdapter):
    """mock `happy_001`은 선택·응답과 무관하게 FINAL PASS + ReportPackage를 준다. 합성 후보로 command
    규칙만 보는 테스트는 Package가 없는 상태로 둔다 — 성공 뒤 READY 재확인(§5)이 끼어들지 않게."""

    def get_report_package(self):
        return None

    def get_requirement_report(self, scope):
        return None if scope == "FINAL_PACKAGE" else super().get_requirement_report(scope)


def _candidate(cid: str, rank: int) -> Candidate:
    return Candidate(candidate_id=cid, at=None, at_provenance=None, observed="", thumb_ref=None, rank=rank)


def _store_with_selected_case() -> tuple[CaseStore, CaseAggregate]:
    """후보 2개 중 `cand_a`가 선택된 `EVIDENCE_REVIEW` case."""
    case = CaseAggregate.intake(case_id=CASE_ID, hints={}, manifest_summary={})
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_cmd", input_fingerprint="sha1:cmd-coarse")
    case.receive_candidates([_candidate("cand_a", 1), _candidate("cand_b", 2)])
    case.select_candidate("cand_a")
    jobs.issue_plate_read(case, input_fingerprint="sha1:cmd-plate")
    store = CaseStore()
    store.register(case, _NoPackageAdapter(MOCK_ROOT, "happy_001"))
    return store, case


def _request(case: CaseAggregate, kind: str, payload: dict, **overrides) -> dict:
    return {"case_id": case.case_id, "expected_case_rev": case.case_rev, "kind": kind, "payload": payload, **overrides}


def _state(case: CaseAggregate) -> dict:
    return copy.deepcopy(
        {
            "case_rev": case.case_rev,
            "stage": case.stage,
            "user_reviewed": case.user_reviewed,
            "selection_rev": case.selection_rev,
            "selected": [c.candidate_id for c in case.candidates if c.selected],
            "situation_response": case.situation_response,
            "job_records": case.job_records,
            "correction_records": case.correction_records,
        }
    )


def _reload(store: CaseStore, case: CaseAggregate) -> CaseAggregate:
    """저장소는 복사본을 준다 — command 뒤 상태는 다시 읽어서 확인한다."""
    return store.get_case(case.case_id)


def _mutate(store: CaseStore, case_id: str, fn) -> CaseAggregate:
    """등록 뒤 상태를 바꾸는 준비 단계 — load_for_update → fn → save."""
    case = store.load_for_update(case_id)
    fn(case)
    store.save(case)
    return case


def _assert_rejected(response: dict, code: str) -> None:
    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert response["error"]["message_key"]


def test_handle_command_is_exported_from_case_package():
    assert case_package.handle_command is command.handle_command


# --- SELECT_OTHER_CANDIDATE -------------------------------------------------


def test_select_other_candidate_moves_selection_and_returns_view():
    store, case = _store_with_selected_case()
    rev = case.case_rev

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"}), store=store
    )

    assert response["ok"] is True
    assert response["error"] is None
    assert response["case_view"]["case_rev"] == rev + 1
    assert [c["candidate_id"] for c in response["case_view"]["candidates"] if c["selected"]] == ["cand_b"]
    assert _reload(store, case).correction_records[-1]["kind"] == "OTHER_CANDIDATE"


def test_select_already_selected_candidate_is_not_allowed():
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_a"}), store=store
    )

    _assert_rejected(response, "case.command.not_allowed")
    assert _state(_reload(store, case)) == before


def test_select_unknown_candidate_is_unknown_target():
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_zzz"}), store=store
    )

    _assert_rejected(response, "case.command.unknown_target")
    assert _state(_reload(store, case)) == before


def test_select_before_candidate_review_is_not_allowed():
    case = CaseAggregate.intake(case_id="case_cmd_early", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates([_candidate("cand_a", 1), _candidate("cand_b", 2)])
    store = CaseStore()
    store.register(case, MockFixtureAdapter(MOCK_ROOT, "happy_001"))

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"}), store=store
    )

    _assert_rejected(response, "case.command.not_allowed")
    assert _reload(store, case).stage == "CANDIDATE_REVIEW"


# --- RECORD_SITUATION_RESPONSE ----------------------------------------------


def test_record_situation_response_is_filled_by_case_clock():
    store, case = _store_with_selected_case()
    rev = case.case_rev

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "USER_UNSURE"}), store=store
    )

    assert response["ok"] is True
    assert response["case_view"]["case_rev"] == rev + 1
    response_record = _reload(store, case).situation_response
    assert response_record["value"] == "USER_UNSURE"
    assert response_record["candidate_ref"]["ref"] == "cand_a"
    assert response_record["responded_at"]  # web이 아니라 case가 채운다(§5)


def test_record_situation_response_rejects_corrected_in_this_version():
    """`CORRECTED`는 입력형 판본에서 `SITUATION_CHANGE`와 함께 연다(§5)."""
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CORRECTED"}), store=store
    )

    _assert_rejected(response, "case.command.invalid_payload")
    assert _state(_reload(store, case)) == before


def test_record_situation_response_without_selection_is_not_allowed():
    case = CaseAggregate.intake(case_id="case_cmd_nosel", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates([_candidate("cand_a", 1)])
    store = CaseStore()
    store.register(case, MockFixtureAdapter(MOCK_ROOT, "happy_001"))

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store
    )

    _assert_rejected(response, "case.command.not_allowed")
    assert _reload(store, case).situation_response is None


# --- MARK_REVIEWED ----------------------------------------------------------


def test_mark_reviewed_outside_ready_is_not_allowed():
    """domain `mark_reviewed()`에는 stage 가드가 없다 — command 층이 `READY`만 받는다(§10)."""
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(_request(case, "MARK_REVIEWED", {}), store=store)

    _assert_rejected(response, "case.command.not_allowed")
    assert _state(_reload(store, case)) == before


def test_mark_reviewed_in_ready_sets_flag():
    store, case = _store_with_selected_case()
    case = _mutate(store, case.case_id, lambda c: c.mark_ready(report_package={"package_id": "pkg_cmd"}))
    rev = case.case_rev

    response = command.handle_command(_request(case, "MARK_REVIEWED", {}), store=store)

    assert response["ok"] is True
    assert _reload(store, case).user_reviewed is True
    assert response["case_view"]["case_rev"] == rev + 1


# --- RUN_NOTICE_ACTION ------------------------------------------------------


def test_run_notice_action_issues_job_for_action_on_screen():
    store, case = _store_with_selected_case()
    jobs_before = len(case.job_records)

    response = command.handle_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )

    assert response["ok"] is True
    records = _reload(store, case).job_records
    assert len(records) == jobs_before + 1
    issued = records[-1]
    # 계약 B절 §7 매핑: RETRY_PLATE_READ → 새 job_id의 PLATE_READ, force_rerun 불필요.
    assert issued["kind"] == "PLATE_READ"
    assert issued["force_rerun"] is False
    assert issued["input_fingerprint"] == "sha1:cmd-plate"
    assert issued["job_id"] != records[-2]["job_id"]


def test_run_notice_action_not_on_screen_is_unknown_target():
    """허용 조건은 「화면에 그 버튼이 떠 있었는가」다(§5)."""
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
    )

    _assert_rejected(response, "case.command.unknown_target")
    assert _state(_reload(store, case)) == before


def test_run_notice_action_with_action_not_on_that_notice_is_unknown_target():
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_SEARCH"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )

    _assert_rejected(response, "case.command.unknown_target")
    assert _state(_reload(store, case)) == before


# --- 공통: 검사 순서와 원자성(§6) ----------------------------------------------


def test_stale_revision_is_rejected_with_current_view():
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"}, expected_case_rev=case.case_rev - 1),
        store=store,
    )

    _assert_rejected(response, "case.command.stale_revision")
    assert response["case_view"]["case_rev"] == case.case_rev
    assert _state(_reload(store, case)) == before


def test_stale_revision_is_reported_before_target_checks():
    store, case = _store_with_selected_case()

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_zzz"}, expected_case_rev=case.case_rev - 1),
        store=store,
    )

    _assert_rejected(response, "case.command.stale_revision")


def test_unknown_case_returns_null_view():
    store, case = _store_with_selected_case()

    response = command.handle_command(
        _request(case, "MARK_REVIEWED", {}, case_id="case_missing"), store=store
    )

    _assert_rejected(response, "case.command.unknown_target")
    assert response["case_view"] is None


def test_invalid_payload_is_reported_before_unknown_case():
    store, case = _store_with_selected_case()

    response = command.handle_command(
        _request(case, "SELECT_OTHER_CANDIDATE", {}, case_id="case_missing"), store=store
    )

    _assert_rejected(response, "case.command.invalid_payload")
    assert response["case_view"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "DELETE_CASE"},
        {"expected_case_rev": "3"},
        {"expected_case_rev": True},
        {"payload": None},
        {"kind": "MARK_REVIEWED", "payload": {"extra": 1}},
        {"kind": "RUN_NOTICE_ACTION", "payload": {"notice_code": "x", "action": "MANUAL_PLATE_INPUT"}},
    ],
)
def test_malformed_request_is_invalid_payload(overrides):
    store, case = _store_with_selected_case()
    before = _state(_reload(store, case))
    request = {**_request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"}), **overrides}

    response = command.handle_command(request, store=store)

    _assert_rejected(response, "case.command.invalid_payload")
    assert response["case_view"]["case_id"] == case.case_id
    assert _state(_reload(store, case)) == before


# --- 성공 뒤 PACKAGE_READY 재확인(§5) ----------------------------------------
# transport가 `mark_ready_if_package_ready()`를 부르면 통로에 판단이 들어간다(#106). command가
# 성공하고 stage가 `EVIDENCE_REVIEW`면 case가 #167 gate를 다시 본다.


def _real_happy_store() -> tuple[CaseStore, CaseAggregate]:
    """real(fixture) 경로 — `observation_facts=None`. 최종 영상 관찰(I4)은 FINAL을 막지 않는다(#280)."""
    scope = MockFixtureAdapter(MOCK_ROOT, "happy_001").get_analysis_scopes()[0]
    case = CaseAggregate.intake(case_id="case_cmd_real", hints={}, manifest_summary={})
    real = RealAdapter(case_id=case.case_id, case=case, search_scope=scope, mock_root=MOCK_ROOT)
    case.start_search()
    jobs.issue_coarse_search(case, scope_ref="scope_h001", input_fingerprint="sha1:h001-coarse-search")
    service.receive_search_candidates(case, real)
    case.select_top_ranked()
    store = CaseStore()
    store.register(case, real)
    return store, case


def _mock_happy_store() -> tuple[CaseStore, CaseAggregate]:
    """mock `happy_001`의 실제 후보를 고른 case — FINAL PASS + ReportPackage가 준비된 상태."""
    adapter = MockFixtureAdapter(MOCK_ROOT, "happy_001")
    case = CaseAggregate.intake(case_id="case_cmd_mock_ready", hints={}, manifest_summary={})
    case.start_search()
    service.receive_search_candidates(case, adapter)
    case.select_top_ranked()
    store = CaseStore()
    store.register(case, adapter)
    return store, case


def test_successful_command_moves_to_ready_when_package_is_ready():
    store, case = _mock_happy_store()
    rev = case.case_rev

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store
    )

    assert response["ok"] is True
    assert response["case_view"]["stage"] == "READY"
    assert response["case_view"]["package"] is not None
    assert response["case_view"]["case_rev"] == rev + 2  # 응답 +1, READY 전이 +1


def test_mark_reviewed_follows_in_one_flow():
    """상황 응답 → READY → 최종 확인이 transport 판단 없이 이어진다."""
    store, case = _mock_happy_store()
    first = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store
    )

    second = command.handle_command(
        _request(case, "MARK_REVIEWED", {}, expected_case_rev=first["case_view"]["case_rev"]), store=store
    )

    assert second["ok"] is True
    assert second["case_view"]["user_reviewed"] is True


class _PackageNeverReady(MockFixtureAdapter):
    """FINAL이 판정되지 않아 Package가 끝내 없는 adapter — 어느 rule이 막는지와 무관하게 gate만 본다."""

    def __init__(self) -> None:
        super().__init__(MOCK_ROOT, "happy_001")

    def get_report_package(self):
        return None

    def get_requirement_report(self, scope):
        return None if scope == "FINAL_PACKAGE" else super().get_requirement_report(scope)


def test_command_stays_in_evidence_review_when_package_blocked():
    adapter = _PackageNeverReady()
    case = CaseAggregate.intake(case_id="case_cmd_blocked", hints={}, manifest_summary={})
    case.start_search()
    service.receive_search_candidates(case, adapter)
    case.select_top_ranked()
    store = CaseStore()
    store.register(case, adapter)
    rev = case.case_rev

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store
    )

    assert response["ok"] is True
    assert response["case_view"]["stage"] == "EVIDENCE_REVIEW"
    assert response["case_view"]["package"] is None
    assert response["case_view"]["case_rev"] == rev + 1


def test_real_path_moves_to_ready_without_report_video_observation():
    """#280 — real 경로는 `observation_facts=None`이지만 I4 부재만으로 FINAL이 막히지 않는다."""
    store, case = _real_happy_store()
    rev = case.case_rev

    response = command.handle_command(
        _request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store
    )

    assert response["ok"] is True
    assert response["case_view"]["stage"] == "READY"
    assert response["case_view"]["package"] is not None
    assert response["case_view"]["case_rev"] == rev + 2  # 응답 +1, READY 전이 +1


def test_rejected_command_does_not_move_to_ready():
    """실패한 command는 아무것도 바꾸지 않는다(§6) — Package가 준비돼 있어도 전이하지 않는다."""
    store, case = _mock_happy_store()
    before = _state(_reload(store, case))

    response = command.handle_command(
        _request(case, "MARK_REVIEWED", {}), store=store  # EVIDENCE_REVIEW라 not_allowed
    )

    assert response["ok"] is False
    assert _state(_reload(store, case)) == before
    assert _reload(store, case).stage == "EVIDENCE_REVIEW"


# --- READY에서 다시 조립되는 변경(값 정정·상황 응답) ----------------------------------------
# READY는 PACKAGE_READY 파생 gate다(CaseView 계약 §10-9: READY면 requirements_package가 PASS/WARN).
# 다시 조립되는 변경이 오면 domain이 EVIDENCE_REVIEW로 내리고, 성공 뒤 재확인이 gate가 여전히
# 성립할 때만 다시 올린다. user_reviewed는 필드 수정과 별개다(계약 L264 · #173 값별 경계표).


class _PackageOnlyWhenConfirmed(MockFixtureAdapter):
    """응답이 CONFIRMED일 때만 Package가 준비되는 adapter — READY 뒤 응답이 바뀌면 gate가 깨진다."""

    def __init__(self, case: CaseAggregate) -> None:
        super().__init__(MOCK_ROOT, "happy_001")
        self._case = case

    def bind_case(self, case: CaseAggregate) -> None:
        self._case = case  # 요청마다 방금 로드한 aggregate를 붙인다(store.get_adapter)

    def _confirmed(self) -> bool:
        return (self._case.situation_response or {}).get("value") == "CONFIRMED"

    def get_report_package(self):
        return super().get_report_package() if self._confirmed() else None

    def get_requirement_report(self, scope):
        if scope == "FINAL_PACKAGE" and not self._confirmed():
            return None
        return super().get_requirement_report(scope)


def _reviewed_ready(store: CaseStore, case: CaseAggregate) -> None:
    first = command.handle_command(_request(case, "RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}), store=store)
    assert first["case_view"]["stage"] == "READY"
    second = command.handle_command(_request(_reload(store, case), "MARK_REVIEWED", {}), store=store)
    assert second["case_view"]["user_reviewed"] is True


def test_response_in_ready_stays_ready_when_package_still_ready():
    store, case = _mock_happy_store()
    _reviewed_ready(store, case)
    rev = _reload(store, case).case_rev

    response = command.handle_command(_request(_reload(store, case), "RECORD_SITUATION_RESPONSE", {"value": "USER_UNSURE"}), store=store)

    assert response["ok"] is True
    assert response["case_view"]["stage"] == "READY"
    assert response["case_view"]["package"] is not None
    assert response["case_view"]["user_reviewed"] is True
    assert response["case_view"]["case_rev"] == rev + 2  # 응답 +1, 다시 READY 전이 +1


def test_response_in_ready_drops_to_evidence_review_when_package_gone():
    """READY인데 Package가 없는 CaseView를 내지 않는다(§10-9 · orchestration 지표 I1)."""
    adapter_case = CaseAggregate.intake(case_id="case_cmd_gated", hints={}, manifest_summary={})
    adapter = _PackageOnlyWhenConfirmed(adapter_case)
    adapter_case.start_search()
    service.receive_search_candidates(adapter_case, adapter)
    adapter_case.select_top_ranked()
    store = CaseStore()
    store.register(adapter_case, adapter)
    _reviewed_ready(store, adapter_case)
    rev = _reload(store, adapter_case).case_rev

    response = command.handle_command(
        _request(_reload(store, adapter_case), "RECORD_SITUATION_RESPONSE", {"value": "USER_UNSURE"}), store=store
    )

    assert response["ok"] is True
    assert response["case_view"]["stage"] == "EVIDENCE_REVIEW"
    assert response["case_view"]["package"] is None
    assert response["case_view"]["user_reviewed"] is True
    assert response["case_view"]["case_rev"] == rev + 1  # 내려가는 것은 같은 요청의 결과 — 따로 올리지 않는다


# --- 이번 command로 append된 JobRecord (8-7, HTTP API Contract §5.3) ----------------


def test_execute_command_returns_job_record_appended_by_this_command():
    """composition root는 이 목록마다 enqueue하고 200/202를 정한다 — 응답 body에는 싣지 않는다."""
    store, case = _store_with_selected_case()

    result = command.execute_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )

    assert result.response["ok"] is True
    assert result.appended_job_records == [_reload(store, case).job_records[-1]]
    assert set(result.response) == {"ok", "error", "case_view"}


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"}),
        ("RECORD_SITUATION_RESPONSE", {"value": "CONFIRMED"}),
    ],
)
def test_execute_command_without_job_returns_empty_list(kind, payload):
    store, case = _store_with_selected_case()

    result = command.execute_command(_request(case, kind, payload), store=store)

    assert result.response["ok"] is True
    assert result.appended_job_records == []


def test_execute_command_mark_reviewed_returns_empty_list():
    store, case = _store_with_selected_case()
    case = _mutate(store, case.case_id, lambda c: c.mark_ready(report_package={"package_id": "pkg_cmd"}))

    result = command.execute_command(_request(case, "MARK_REVIEWED", {}), store=store)

    assert result.response["ok"] is True
    assert result.appended_job_records == []


@pytest.mark.parametrize(
    "make_request",
    [
        lambda case: {"case_id": case.case_id, "kind": "MARK_REVIEWED", "payload": {}},  # invalid_payload
        lambda case: _request(case, "MARK_REVIEWED", {}, case_id="case_missing"),  # unknown_target(case)
        lambda case: _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}, expected_case_rev=case.case_rev - 1),  # stale_revision
        lambda case: _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),  # unknown_target(대상) — 화면에 버튼 없음
        lambda case: _request(case, "MARK_REVIEWED", {}),  # not_allowed — EVIDENCE_REVIEW
    ],
)
def test_execute_command_rejected_returns_empty_list(make_request):
    store, case = _store_with_selected_case()

    result = command.execute_command(make_request(case), store=store)

    assert result.response["ok"] is False
    assert result.appended_job_records == []


def test_execute_command_returned_records_do_not_alias_case_state():
    store, case = _store_with_selected_case()
    result = command.execute_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )
    job_id = _reload(store, case).job_records[-1]["job_id"]

    result.appended_job_records[0]["job_id"] = "tampered"

    assert _reload(store, case).job_records[-1]["job_id"] == job_id


def test_handle_command_returns_execute_command_response():
    store, case = _store_with_selected_case()
    request = _request(case, "SELECT_OTHER_CANDIDATE", {"candidate_id": "cand_b"})

    response = command.handle_command(request, store=store)

    assert response["ok"] is True
    assert set(response) == {"ok", "error", "case_view"}


def test_execute_command_is_exported_from_case_package():
    assert case_package.execute_command is command.execute_command
    assert case_package.CommandResult is command.CommandResult


# --- 202 응답의 case_view에 방금 append한 job (8-11, HTTP API Contract §5.3) ----------------


def test_command_response_view_shows_appended_job_as_pending():
    store, case = _store_with_selected_case()

    result = command.execute_command(
        _request(case, "RUN_NOTICE_ACTION", {"notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ"}),
        store=store,
        notices=[PLATE_READ_FAILED],
    )

    appended = result.appended_job_records[0]
    # 재시도로 대체된 이전 PLATE_READ는 빠지고, 새 job만 실행 기록 없이 PENDING으로 보인다.
    assert result.response["case_view"]["running_jobs"] == [
        {"job_id": appended["job_id"], "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "PENDING"}
    ]
