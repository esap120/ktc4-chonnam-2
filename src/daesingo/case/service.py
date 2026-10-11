"""orchestration 진입점 — `ModuleAdapter`(Mock 또는 Real)로부터 데이터를 가져와 `case`의
도메인 상태(`CaseAggregate`)에 반영하거나 `CaseView`를 조립하는, 재사용 가능한 실행 코드.

## 왜 필요한가

지금까지 "adapter로 데이터 가져오기 → 도메인 메서드 호출 → 결과 반영"은 시나리오별 스모크
테스트(`tests/test_scenario_*_smoke.py`) 안에서 손으로 짜여 있었다 — 테스트가 곧
orchestration 흐름의 유일한 실행 경로였다. 이 모듈은 그 흐름 중 "adapter 값을 그대로
옮기는" 부분만 재사용 가능한 함수로 뽑아낸다. `RealAdapter`가 모듈별로 채워지면, 이
파일이나 `domain.py`/`jobs.py`/`view.py`는 건드리지 않고 호출하는 쪽에서 어댑터
인스턴스만 `MockFixtureAdapter(...)`에서 `RealAdapter(...)`로 바꾸면 된다.

## 여기 없는 것

- **자동 전체 진행(auto-run)은 없다.** 어떤 job을 언제 발주할지, 언제 재시도·정정을
  받아들일지는 여전히 호출자(테스트, 또는 앞으로 만들어질 실제 worker loop)의 책임이다
  — 시나리오마다 분기가 다르기 때문에(happy/unknown-abstain/infra-failure 등) 이 파일이
  임의로 "다음 단계"를 추측하지 않는다.
- evidence 판정 로직, OCR 판단, 업로드 규정 등 다른 모듈의 정책은 여기서 재구현하지
  않는다 — `adapters.py`와 마찬가지로 "옮기기만" 한다.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from daesingo.case import jobs
from daesingo.case.analysis_start import InitialSearchBudget, hints_from_result, reflect_hint_extraction
from daesingo.case.adapters import ModuleAdapter
from daesingo.case.domain import Candidate, CaseAggregate
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimelineSource
from daesingo.case.view import _belongs_to_current_selection, build_case_view, execution_failed
from daesingo.evidence import AWAIT_SITUATION_RESPONSE, NOT_ASSEMBLED


def receive_search_candidates(case: CaseAggregate, adapter: ModuleAdapter) -> list[Candidate]:
    """`adapter.get_candidate_events()`를 읽어 `Candidate`로 변환하고
    `case.receive_candidates()`에 반영한다. 반환값은 호출자가 (예: 로그·검증용으로)
    그대로 참고할 수 있게 넘겨준다 — `case` 상태 반영은 이 함수 안에서 이미 끝나 있다.

    `at`는 여기서 채우지 않는다 — 절대시각 확정은 readout/evidence 쪽 책임이라 `search`의
    `CandidateEvent`에는 없는 값이다. `at_provenance`는 `at is None`인 이 상태를 위해 이미
    등록된 case 소유 enum 값(`recording.timeline_relative_only`,
    `docs/modules/case/decisions/candidate-at-provenance-label-key.md`)을 쓴다 — `None`을
    두면 계약(`caseView.ts`/contract 문서 §7)이 기대하는 non-null과 어긋난다(이슈 #104).
    """
    raw_candidates = adapter.get_candidate_events()
    if str(adapter.get_candidate_search_outcome()) == "FAILED":
        # 실패 Run(후보 0개)은 투영 대상을 바꾸지 않는다 — 계약 §7 `RESUME_SEARCH` 행.
        case.record_candidate_search_failure()
        return []
    candidates = [
        Candidate(
            candidate_id=c["candidate_id"],
            at=None,
            at_provenance="recording.timeline_relative_only",
            observed=c["summary"],
            thumb_ref=c["thumbnail_ref"],
            rank=c["rank"],
            # span 좌표는 생성 당시 timeline revision 기준이다 — stale 판정과 marker_ms의 근거(#184).
            representative_ms=c["span"]["representative_ms"],
            timeline_revision=c["span"]["timeline_revision"],
        )
        for c in raw_candidates
    ]
    case.receive_candidates(candidates)
    return candidates


def receive_hint_extraction(case: CaseAggregate, result: dict[str, Any]) -> None:
    """단서 구조화(`HINT_EXTRACT`) 결과를 `case.hints`에 반영한다 — case-command Draft §11.

    `OK`면 `*_hint` 4개를 `hints` 4개 키로 옮긴다(일부만 있어도 된다). 빈 문자열은 단서가 아니라 `None`
    으로 둔다. `ABSTAINED`(모델이 전부 보류) · `FAILED`(호출 · 파싱 실패)면 결과에 값이 있어도 쓰지 않고
    4개 모두 `None` — 값을 지어내지 않고 빈 단서로 탐색을 이어 간다. 그 밖의 상태는 결과 모양이 바뀐
    것이라 `ValueError`로 멈춘다. 결과 모양은 #210 Search 의견을 가정했고 Search PR에서 맞춘다. 매핑은 `analysis_start.hints_from_result()`.

    `AnalysisScope` · `COARSE_SEARCH` 발주는 여기서 하지 않는다 — scope 기본값과 첫 발주 fingerprint가
    정해지지 않았다(Draft §11 미결).
    """
    case.record_extracted_hints(hints_from_result(result))


@dataclass
class AdapterSnapshot:
    """`CaseView` 조립에 필요한, `CaseAggregate`에는 저장되지 않는 downstream 값들의
    한 시점 스냅샷. evidence/requirements/package는 case 상태로 들고 있지 않고 매번
    adapter에서 새로 읽는다 — 다른 모듈이 같은 case에 대해 값을 갱신했으면 다음
    `fetch_case_view_inputs()` 호출에서 그대로 반영돼야 하기 때문이다.
    """

    evidence_record: dict[str, Any] | None
    requirement_report_evidence: dict[str, Any] | None
    requirement_report_package: dict[str, Any] | None
    report_package: dict[str, Any] | None
    # `evidence.plate_preview_ref`(#47)의 원천 — 번호판 근거 프레임을 찾는 데만 쓴다.
    plate_readouts: list[dict[str, Any]] = field(default_factory=list)
    # `readout.overlay_*` notice의 원천 — 현재 선택 후보의 가장 나중 판독만 본다.
    overlay_time_readouts: list[dict[str, Any]] = field(default_factory=list)
    plate_read_status: str | None = None
    # 선택된 후보 Fine 결과의 소비 판정 — 음성 결과 notice(#168 [A])의 원천.
    visual_evidence_decision: str | None = None
    # `evidence.plate_abstained`(#172 D-3)의 발동 근거 — CaseView 값만으로는 번호판 보류(1·2)와
    # 읽지 못함(1·3)이 같게 보인다. notice 판단에만 쓰고 CaseView에 싣지 않는다.
    evidence_needs: list[dict[str, Any]] = field(default_factory=list)
    # 상황 응답 대기 중 evidence가 계산한 상황 독립 값 — `evidence` 부분 투영(`record_id=null`, #239)의 원천.
    independent_facts: dict[str, Any] | None = None


def fetch_case_view_inputs(adapter: ModuleAdapter) -> AdapterSnapshot:
    """`build_case_view()`가 요구하는 4개 입력을 adapter에서 한 번에 가져온다."""
    return AdapterSnapshot(
        evidence_record=adapter.get_evidence_record(),
        requirement_report_evidence=adapter.get_requirement_report("EVIDENCE"),
        requirement_report_package=adapter.get_requirement_report("FINAL_PACKAGE"),
        report_package=adapter.get_report_package(),
        plate_readouts=adapter.get_plate_readouts(),
        overlay_time_readouts=adapter.get_overlay_time_readouts(),
        plate_read_status=adapter.get_plate_read_status(),
        visual_evidence_decision=adapter.get_visual_evidence_decision(),
        evidence_needs=adapter.get_evidence_needs(),
        independent_facts=adapter.get_independent_facts(),
    )


_PACKAGE_READY_READINESS = frozenset({"PASS", "WARN"})


def _inputs_for(case: CaseAggregate, adapter: ModuleAdapter | None) -> AdapterSnapshot:
    """선택된 candidate가 없으면(탐색 중 · 후보 0개) downstream 값이 아직 없다 — adapter를
    조회하지 않고 빈 스냅샷을 돌려준다. real adapter는 선택 전 evidence 조회를 명확히 실패시키므로
    (#92 안전장치), 이 판단을 adapter가 아니라 case 상태로 먼저 한다. 선택이 있으면 그대로
    `fetch_case_view_inputs()`다."""
    if not any(c.selected for c in case.candidates):
        return AdapterSnapshot(
            evidence_record=None,
            requirement_report_evidence=None,
            requirement_report_package=None,
            report_package=None,
        )
    if adapter is None:
        raise AdapterNotAttached(f"선택된 후보가 있는데 adapter가 없다: case_id={case.case_id!r}")
    return fetch_case_view_inputs(adapter)


def mark_ready_if_package_ready(case: CaseAggregate, adapter: ModuleAdapter | None) -> bool:
    """`PACKAGE_READY` gate가 성립할 때만 `READY`로 올린다(#167). 올렸으면 `True`.

    CaseView 계약 B절: `READY` = FINAL `RequirementReport`가 `PASS`/`WARN`이고 ReportPackage가
    있는 시점(#171 C 결정). evidence·Package는 adapter가 downstream 결과로 갖고 있어, 스냅샷을
    읽어 판단하고 Package를 domain `mark_ready()`에 넘긴다(domain은 Package 없는 전이를
    거부한다). Package가 막혔거나
    (상황 응답 전 등) evidence가 조립되지 않았으면(`NOT_ASSEMBLED`) stage를 바꾸지 않는다.
    그 결과를 어느 화면으로 보일지는 #168·#171 결정 몫이라 여기서 정하지 않는다.
    """
    snapshot = _inputs_for(case, adapter)
    # RequirementReport의 판정 필드는 `overall`이다(CaseView에서 `readiness`로 옮겨 싣는다).
    final = snapshot.requirement_report_package or {}
    if snapshot.report_package is None or final.get("overall") not in _PACKAGE_READY_READINESS:
        return False
    # 현재 선택 context의 결과일 때만 — CaseView가 evidence를 거르는 기준(#191)과 같다. 다르면 stage는
    # READY인데 CaseView의 evidence·package가 null이 된다. 결과가 늦게 도착하는 경로(W7 6.6순위)에서
    # 이전 선택의 Package가 올 수 있다.
    selected = next((c for c in case.candidates if c.selected), None)
    if snapshot.evidence_record is None or not _belongs_to_current_selection(case, selected, snapshot.evidence_record):
        return False
    case.mark_ready(report_package=snapshot.report_package)
    return True


def build_view_from_adapter(
    case: CaseAggregate,
    adapter: ModuleAdapter | None,
    *,
    job_executions: list[dict[str, Any]] | None = None,
    notices: list[dict[str, Any]] | None = None,
    visual_verify_status: str | None = None,
) -> dict[str, Any]:
    """`fetch_case_view_inputs()` + `build_case_view()`를 이어붙인 편의 함수 —
    스모크 테스트에서 매번 반복되던 4줄을 한 호출로 줄인다. `case`(상태)와 `adapter`
    (downstream 스냅샷 소스)만 있으면 `CaseView`를 조립할 수 있다는 것이 이 함수가
    보이는 계약이다.

    `running_jobs`는 case가 정산 기록으로 계산하고(`view.derive_running_jobs`), 실행 상태만
    `job_executions`로 받는다. `notices`는 adapter가 아니라 호출자가 직접 안다(모듈 docstring
    「여기 없는 것」과 동일한 이유). 둘 다 그대로 `build_case_view()`에 전달만 한다. `visual_verify_status`(선택 후보 Fine의 대표
    `JobExecution.status`)도 같은 이유로 호출자가 넘긴다 — worker 경로에서는
    `view.representative_execution_status(..., "FINE_VERIFY")`가 만든다.

    예외는 `derive_notices()` 하나 — 조립된 `CaseView` 값(과 adapter의 Fine 판정)만으로 발동
    조건이 정해지는 notice는 호출자가 알 필요가 없으므로 여기서 붙인다.

    선택 전(탐색 중 · 후보 0개)에는 adapter의 downstream 값을 조회하지 않는다(`_inputs_for()`).
    """
    snapshot = _inputs_for(case, adapter)
    view = build_case_view(
        case,
        evidence_record=snapshot.evidence_record,
        requirement_report_evidence=snapshot.requirement_report_evidence,
        requirement_report_package=snapshot.requirement_report_package,
        report_package=snapshot.report_package,
        plate_readouts=snapshot.plate_readouts,
        job_executions=job_executions,
        notices=notices,
        plate_read_status=snapshot.plate_read_status,
        visual_evidence_decision=snapshot.visual_evidence_decision,
        visual_verify_status=visual_verify_status,
        independent_facts=snapshot.independent_facts,
    )
    return derive_notices(
        view,
        evidence_needs=snapshot.evidence_needs,
        visual_evidence_decision=snapshot.visual_evidence_decision,
        plate_read_retry_basis=jobs.latest_job_record(case, "PLATE_READ") is not None,
        visual_verify_status=visual_verify_status,
        overlay_time_readouts=snapshot.overlay_time_readouts,
    )


# `contract-job-record-case-view.md` B절 `notices[].code` 표의 2026-09-14 등재값(이슈 #47/#48).
# 접두어 `evidence.`는 발동 근거(`search_keyword`)를 만든 모듈을 뜻하는 명명 규칙이며,
# CaseView에 싣는 것은 case다.
LOCATION_SEARCH_KEYWORD_MISSING_NOTICE: dict[str, Any] = {
    "code": "evidence.location_search_keyword_missing",
    "severity": "INFO",
    "blocking": False,
    "message_key": "notice.location_search_keyword_missing",
    "actions": [],
}


# 후보 탐색 실패(PR #187 리뷰). 계약 B절 `notices[].code` 등재(2026-09-28).
CANDIDATE_SEARCH_FAILED_NOTICE: dict[str, Any] = {
    "code": "search.candidate_search_failed",
    "severity": "ERROR",
    "blocking": True,
    "message_key": "notice.candidate_search_failed",
    "actions": ["RETRY_SEARCH"],
}


# 번호판 판독 실행 실패(#172 [D] 4a). mock fixture(`scenario_infra_failure_001` rev2)가 이미 쓰는
# 모양 그대로다 — 계약 B절 `notices[].code` 등재(2026-09-28).
PLATE_READ_FAILED_NOTICE: dict[str, Any] = {
    "code": "readout.plate_read_failed",
    "severity": "ERROR",
    "blocking": True,
    "message_key": "notice.plate_read_failed_retry_exhausted",
    "actions": ["RETRY_PLATE_READ"],
}


# `contract-job-record-case-view.md` B절 `notices[].code` 등재값(2026-09-28, #171 C-2 Case 결정).
# 응답 버튼은 notice action이 아니라 #106 command라 `actions`는 비운다.
SITUATION_RESPONSE_PENDING_NOTICE: dict[str, Any] = {
    "code": "case.situation_response_pending",
    "severity": "INFO",
    "blocking": False,
    "message_key": "notice.situation_response_pending",
    "actions": [],
}


# 후보 0개(검색은 성공, 결과 없음). 모양은 `scenario_empty_001` fixture가 먼저 쓰던 값 그대로다 —
# 계약 B절 `notices[].code` 등재(2026-09-29). 단서 수정·재검색이 이 화면의 출구다(이슈 #31 W-1).
NO_CANDIDATES_NOTICE: dict[str, Any] = {
    "code": "search.no_candidates",
    "severity": "INFO",
    "blocking": False,
    "message_key": "notice.search_no_candidates",
    "actions": ["EDIT_HINT", "RETRY_SEARCH"],
}


# 음성 결과(#168 [A] 후속, @uminshin 요청). 계약 B절 `notices[].code` 등재(2026-09-29). 접두어는
# 판정(`NOT_ASSEMBLED`)을 만든 evidence(`disposition.py`)를 따른다. 출구(「다른 후보 보기」)는
# 결과 화면 1차 명령이라 `actions`는 비운다.
VISUAL_EVENT_NOT_OBSERVED_NOTICE: dict[str, Any] = {
    "code": "evidence.visual_event_not_observed",
    "severity": "INFO",
    "blocking": False,
    "message_key": "notice.visual_event_not_observed",
    "actions": [],
}


# Fine 실행 실패(고도화 문서 8-14, #244 R-1 후속). 계약 B절 `notices[].code` 등재(2026-10-04). 접두어는
# Fine Run을 만드는 search를 따른다. 같은 후보를 다시 Fine하는 action은 닫힌 `actions[]` 목록에 없어
# 비운다 — 출구는 결과 화면 1차 명령 「다른 후보 보기」다(음성 결과와 같다).
VISUAL_VERIFY_FAILED_NOTICE: dict[str, Any] = {
    "code": "search.visual_verify_failed",
    "severity": "ERROR",
    "blocking": True,
    "message_key": "notice.visual_verify_failed",
    "actions": [],
}


# `contract-job-record-case-view.md` B절 `notices[].code` 등재값(2026-09-30, #172 D-3 case 후속).
# 모양은 `scenario_plate_reread_001` fixture 값이되, `MANUAL_PLATE_INPUT`은 입력형 command 판본(#106)
# 전에는 보낼 경로가 없어 `actions`를 비운다.
PLATE_ABSTAINED_NOTICE: dict[str, Any] = {
    "code": "evidence.plate_abstained",
    "severity": "WARN",
    "blocking": False,
    "message_key": "notice.plate_abstained",
    "actions": [],
}


# overlay 판독이 정상 종료했지만 시각을 얻지 못한 갈래(readout `failure-taxonomy.md` 「`CaseView.notices[].code`
# 매핑」, #31 A-1). `observation.reason.code`와 1:1이고(점 → 밑줄) 셋을 합치지 않는다 — 「화면에 시각이 없다」
# (사실)와 「확인하지 못했다」(모름)는 다른 말이다(`core-user-flow.md` §5). 실행 실패가 아니라 `INFO`이고,
# 사용자가 할 시각 확인은 `evidence.time_*` notice가 나른다.
OVERLAY_REASON_NOTICES: dict[str, dict[str, Any]] = {
    reason: {
        "code": f"readout.overlay_{detail}",
        "severity": "INFO",
        "blocking": False,
        "message_key": f"notice.overlay_{detail}",
        "actions": [],
    }
    for reason, detail in (
        ("readout.overlay.not_present", "not_present"),
        ("readout.overlay.presence_undetermined", "presence_undetermined"),
        ("readout.overlay.ocr_failed", "ocr_failed"),
    )
}


def _overlay_notice(view: dict[str, Any], overlay_time_readouts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """현재 선택 후보의 가장 나중 overlay 판독(A§10-7 — 재판독 뒤에는 이전 판독의 notice를 남기지 않는다)의
    `reason.code`에 대응하는 notice. 매핑에 없는 reason은 지어내지 않는다."""
    selected = next((c["candidate_id"] for c in view.get("candidates", []) if c["selected"]), None)
    latest = next((r for r in reversed(overlay_time_readouts) if r.get("candidate_id") == selected), None)
    if selected is None or latest is None:
        return None
    reason = ((latest.get("observation") or {}).get("reason") or {}).get("code")
    return OVERLAY_REASON_NOTICES.get(reason)


def _plate_reread_needed(evidence: dict[str, Any], evidence_needs: list[dict[str, Any]]) -> bool:
    """현재 EvidenceRecord를 basis로 계산된 Needs에 `PLATE_REREAD`가 있는가. 이전 revision의 Need는
    보지 않는다 — 재판독으로 값이 채워진 v2에는 v1의 Need가 남아 있어도 해당하지 않는다."""
    return any(
        (needs.get("basis_record_ref") or {}).get("ref") == evidence["record_id"]
        and any(item.get("kind") == "PLATE_REREAD" for item in needs.get("items", []))
        for needs in evidence_needs
    )


def derive_notices(
    view: dict[str, Any],
    *,
    evidence_needs: list[dict[str, Any]] | None = None,
    visual_evidence_decision: str | None = None,
    plate_read_retry_basis: bool = False,
    visual_verify_status: str | None = None,
    overlay_time_readouts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """조립된 `CaseView` 값만으로 발동 조건이 정해지는 notice를 덧붙인다.

    - `search.candidate_search_failed` — 진행 상태 `coarse_search`가 `FAILED`일 때(PR #187 리뷰).
      evidence 유무와 무관하다.
    - `search.no_candidates` — `stage=CANDIDATE_REVIEW`이고 `candidates`가 비었을 때. 탐색 실패는
      `SEARCHING`에 머물므로(PR #197) 이 조건에 들지 않는다.
    - `readout.plate_read_failed` — 진행 상태 `plate_read`가 `FAILED`일 때(#172 [D]). evidence
      유무와 무관하다. 「다시 판독」(`RETRY_PLATE_READ`)은 발주 근거(같은 kind의 이전 `PLATE_READ`
      JobRecord, `plate_read_retry_basis`)가 있을 때만 싣는다 — 없으면 command가 늘 거부한다
      (case-command 계약 §10). 실행 경로가 없는 action은 싣지 않는다(CaseView 계약 B절).
    - `evidence.location_search_keyword_missing` — 계약 발동 조건이
      `evidence.location_display.search_keyword == null`이다(`location` 존재 여부가 아니다,
      이슈 #48).
    - `case.situation_response_pending` — evidence가 있고, 선택된 후보의
      `situation_confirmation`이 `NOT_ASKED`이며, `package`가 없을 때(#171 C-2). 상황 응답
      전이라 ADR-EVIDENCE-005 D2-c로 Package가 막힌 상태를 결과 화면의 「준비 전」 이유로 알린다.
      evidence가 없어도 adapter가 보고한 Fine 판정이 `AWAIT_SITUATION_RESPONSE`(Fine `UNCERTAIN` +
      응답 전, #165)면 붙인다 — 그렇지 않으면 응답 대기가 조립 중과 같아 보인다(PR #224 리뷰).
    - `evidence.visual_event_not_observed` — evidence가 없고, adapter가 보고한 선택 후보의 Fine
      판정(`visual_evidence_decision`)이 `NOT_ASSEMBLED`일 때(#168 [A]). 음성 결과는 evidence가
      없어 CaseView 값만으로는 조립 전과 구분되지 않으므로 이 판정만 따로 받는다.
    - `search.visual_verify_failed` — evidence가 없고, 호출자가 넘긴 선택 후보 Fine의 대표 실행 상태
      (`visual_verify_status`)가 terminal 실패(`FAILED` · 재시도가 끝난 `STALE`)일 때(8-14). 진행 상태에
      Fine step이 없어 CaseView 값만으로는 조립 전과 구분되지 않는다.
    - `evidence.plate_abstained` — 번호판 값이 없고, `evidence_needs` 중 현재 EvidenceRecord를
      basis로 한 Needs에 `PLATE_REREAD`가 있을 때(#172 D-3: 일부 판독 / `NEEDS_REVIEW`, 1·2).
      CaseView 값만으로는 읽지 못함(1·3)·실행 실패(4a)와 같아 보여서 이것만 CaseView 밖의 입력을
      본다. `evidence_needs`를 넘기지 않으면 붙이지 않는다.
    - `readout.overlay_not_present` · `readout.overlay_presence_undetermined` · `readout.overlay_ocr_failed` —
      현재 선택 후보의 가장 나중 overlay 판독 `observation.reason.code`에 1:1로 대응할 때(readout
      `failure-taxonomy.md`). evidence 유무와 무관하다. `overlay_time_readouts`를 넘기지 않으면 붙이지 않는다.

    evidence에 걸린 notice는 `evidence`가 아직 없으면(EvidenceRecord 조립 전) 판단할 값이 없으므로 붙이지 않는다.
    호출자가 같은 code를 이미 넣었으면 중복하지 않는다. 호출자가 넘긴 `notices` 리스트는
    `build_case_view()`가 그대로 싣기 때문에, 제자리 append 대신 새 리스트로 바꾼다.
    """
    derived = []
    # 후보 탐색 실패는 evidence 유무와 무관하게 알린다 — 실패를 「결과 없음」으로 보이지 않게 한다.
    if any(s["step"] == "coarse_search" and s["state"] == "FAILED" for s in view.get("progress", [])):
        derived.append(CANDIDATE_SEARCH_FAILED_NOTICE)
    if view.get("stage") == "CANDIDATE_REVIEW" and not view.get("candidates"):
        derived.append(NO_CANDIDATES_NOTICE)
    # 번호판 판독 실행 실패는 evidence 유무와 무관하게 알린다(#172 [D]) — 「읽지 못함」은 값
    # 상태(INFO_UNKNOWN)로만 보이고, 실행 실패만 이 notice를 갖는다.
    if any(s["step"] == "plate_read" and s["state"] == "FAILED" for s in view.get("progress", [])):
        derived.append(PLATE_READ_FAILED_NOTICE if plate_read_retry_basis else dict(PLATE_READ_FAILED_NOTICE, actions=[]))
    overlay_notice = _overlay_notice(view, overlay_time_readouts or [])
    if overlay_notice is not None:
        derived.append(overlay_notice)
    evidence = view.get("evidence")
    selected = [c for c in view.get("candidates", []) if c["selected"]]
    awaiting_response = (
        view.get("package") is None and len(selected) == 1 and selected[0]["situation_confirmation"] == "NOT_ASKED"
    )
    if evidence is None and visual_evidence_decision == NOT_ASSEMBLED:
        derived.append(VISUAL_EVENT_NOT_OBSERVED_NOTICE)
    if evidence is None and execution_failed(visual_verify_status):
        derived.append(VISUAL_VERIFY_FAILED_NOTICE)
    # Fine `UNCERTAIN` 응답 대기는 evidence가 없어 CaseView 값만으로는 조립 중과 같아 보인다 —
    # 음성 결과와 같은 방식으로 adapter의 Fine 판정을 본다(PR #224 리뷰).
    if evidence is None and visual_evidence_decision == AWAIT_SITUATION_RESPONSE and awaiting_response:
        derived.append(SITUATION_RESPONSE_PENDING_NOTICE)
    if evidence is not None:
        if evidence["plate_display"]["value"] is None and _plate_reread_needed(evidence, evidence_needs or []):
            derived.append(PLATE_ABSTAINED_NOTICE)
        if evidence["location_display"]["search_keyword"] is None:
            derived.append(LOCATION_SEARCH_KEYWORD_MISSING_NOTICE)
        if awaiting_response:
            derived.append(SITUATION_RESPONSE_PENDING_NOTICE)
    present = {n["code"] for n in view["notices"]}
    additions = [dict(n, actions=list(n["actions"])) for n in derived if n["code"] not in present]
    if additions:
        view["notices"] = [*view["notices"], *additions]
    return view


class AdapterNotAttached(RuntimeError):
    """adapter 없이 등록된 case(빈 case)가 후보를 고른 뒤에도 adapter 없이 조회됐다. 선택 전에는 adapter를
    조회하지 않으므로(`_inputs_for()`) INTAKE · SEARCHING 동안은 adapter가 없어도 된다."""


def create_case(*, store: CaseStore) -> str:
    """빈 case를 만들어 등록하고 `case_id`를 돌려준다(HTTP API Contract §5.1 `POST /cases`).

    `case_id`는 case가 발급한다 — `case_` + uuid4 hex(ASCII 37자). aggregate는 밖으로 내보내지 않는다.
    `decisions/empty-case-and-manifest.md`.
    """
    case_id = f"case_{uuid.uuid4().hex}"
    store.register(CaseAggregate.empty(case_id))
    return case_id


def record_source_registered(
    case_id: str,
    source_asset: dict[str, Any],
    *,
    media_streams: list[dict[str, Any]] | None = None,
    store: CaseStore,
) -> None:
    """recording이 이 case에 등록 · 연결한 원본 1개(`SourceAsset` 계약 dict)를 반영한다(§5.2 upload).

    composition root가 recording 등록과 같은 transaction에서 부른다. `INTAKE`가 아니면
    `SourceNotAccepted` — 같은 transaction이라 recording 등록도 함께 rollback된다.
    `media_streams`(`MediaStream` 계약 dict 목록, recording 등록 결과)를 넘기면 VIDEO 스트림 ref를 함께
    남긴다 — 분석 시작이 여러 원본을 이어 붙일 때 쓴다.
    """
    case = store.load_for_update(case_id)
    case.record_source_registered(source_asset, media_streams)
    store.save(case)


def get_view(
    case_id: str,
    *,
    store: CaseStore,
    job_executions: list[dict[str, Any]] | None = None,
    notices: list[dict[str, Any]] | None = None,
    visual_verify_status: str | None = None,
) -> dict[str, Any]:
    """`web → case.get_view() → CaseView`(`module-architecture.md` §5-1 ⑪, §6 모듈6
    ③)의 실제 진입점. 지금까지 스모크 테스트 안에만 있던 "case_id로 저장된 case를
    찾아서 CaseView를 조립한다"는 마지막 연결을 뽑아냈다.

    `store`를 명시적으로 받는다 — 프로세스 전체가 공유하는 숨은 전역 상태를 두지
    않는다. 여러 요청에 걸쳐 같은 store를 재사용하는 것(예: FastAPI app state)은
    호출자의 책임이다 — 그 배선 자체는 W5/W6 요청 문서가 이번 범위 밖으로 뺀
    "완성된 FastAPI/Worker 배선"에 해당한다.
    """
    case = store.get_case(case_id)
    adapter = store.get_adapter(case_id, case)
    return build_view_from_adapter(
        case, adapter, job_executions=job_executions, notices=notices, visual_verify_status=visual_verify_status
    )


@dataclass(frozen=True)
class ReflectionResult:
    """`receive_hint_extraction_result()`의 결과 — `appended_job_records`는 composition root(Worker T2)가 같은
    transaction에서 enqueue한다(`CommandResult`와 같은 장치). 반영하지 않았으면 `reflected=False` · `[]`."""

    appended_job_records: list[dict[str, Any]]
    reflected: bool


def receive_hint_extraction_result(
    case_id: str,
    result: dict[str, Any],
    *,
    store: CaseStore,
    timelines: CaseTimelineSource,
    budget: InitialSearchBudget | None = None,
) -> ReflectionResult:
    """Worker가 단서 구조화 결과를 반영하는 진입점(`decisions/start-analysis.md` §3-6). `load_for_update` → 반영 →
    성공했을 때만 `save`. 기다리던 `HINT_EXTRACT`가 없으면(중복 결과) 저장하지 않는다. 예외는 그대로 올라가고
    저장되지 않는다 — transaction rollback은 호출자 몫이다(#245 D-2)."""
    case = store.load_for_update(case_id)
    jobs_before = len(case.job_records)
    if not reflect_hint_extraction(case, result, timelines=timelines, budget=budget or InitialSearchBudget()):
        return ReflectionResult(appended_job_records=[], reflected=False)
    store.save(case)
    return ReflectionResult(appended_job_records=copy.deepcopy(case.job_records[jobs_before:]), reflected=True)
