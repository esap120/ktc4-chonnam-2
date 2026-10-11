"""`CaseView` projection — web의 유일한 read dependency.

case가 이미 갖고 있는 상태(`CaseAggregate`)와 다른 모듈이 만든 Canonical Contract
산출물(어댑터를 통해 읽는다)을 조합해서 `case-view/v1.8` 모양으로 안전하게 내보낸다.
evidence/readout 값을 **복사해서 그대로 소유하지 않는다** — 매번 다시 조립한다
(module-architecture.md §4-모듈5 ⑥). 신고 요건 판정(readiness/checks)이나 번호판 OCR
같은 evidence/readout의 판단 자체는 여기서 재계산하지 않고 그대로 옮겨 담기만 한다.

⚠️ 1차 구현 범위: `scenario_happy_001`(happy path)과 `scenario_unknown_abstain_partial_001`
(WARN Package + 위치 미확보 — 2026-09-14, 이슈 #47/#48 후속으로 §11 제외 범위에서 전체
파리티로 승격) 재현에 필요한 필드를 다룬다. 나머지 5개 시나리오(후보 0개/GPS 없음이 아닌
low confidence/Timestamp conflict 단독/Plate abstain 단독/Timeout·partial result)의 표시
규칙은 `docs/modules/case/checklists/phase1-completion-checklist.md` §11에 따라 아직
다루지 않는다.
"""
from __future__ import annotations

from typing import Any

from daesingo.case.domain import CaseAggregate
from daesingo.case.labels import (
    at_provenance_label_key,
    event_type_label,
    evidence_value_info_state,
    location_representative,
    occurred_at_info_state,
    report_type_label,
)
from daesingo.evidence import AWAIT_SITUATION_RESPONSE, NOT_ASSEMBLED

CONTRACT_VERSION = "case-view/v1.8"

_PROGRESS_STEPS = (
    "file_intake",
    "coarse_search",
    "candidate_review",
    "plate_read",
    "overlay_time_read",
    "evidence_assembly",
    "requirement_check",
    "package_assembly",
)

# report_inputs/report_field_states를 만드는 5개 필드의 정식 순서.
# unconfirmed_fields의 순서는 이 순서를 그대로 따른다(임의로 정렬하지 않는다).
_REPORT_FIELDS = ("safety_report_type", "occurred_at", "location", "vehicle_number", "violation_expression")

# `contract-job-record-case-view.md` 헤더 ③ / §13 「JobExecution → CaseView 상태 projection」 —
# QUEUED→PENDING, RUNNING→RUNNING, SUCCEEDED→DONE, FAILED/STALE→FAILED, CANCELLED→PARTIAL
# (CANCELLED은 새 enum 값을 만들지 않고 기존 PARTIAL로 흡수, 이슈 #33 A-2). 이 다섯 매핑
# 자체는 case-view 계약이 소유하는 projection 표라 case 코드가 그대로 옮긴다. 「이 kind의
# 대표 실행이 어떤 JobExecution.status인가」를 고르는 일(가장 나중 job · attempt 최댓값)은
# `representative_execution_status()`가 한다 — JobExecution read port(#245 D-6)는 Contract
# 모양을 그대로 돌려주므로 case가 고른다(A§10-6 · §10-7).
_JOB_EXECUTION_STATUS_TO_PROGRESS_STATE: dict[str, str] = {
    "QUEUED": "PENDING",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "DONE",
    "FAILED": "FAILED",
    "STALE": "FAILED",
    "CANCELLED": "PARTIAL",
}


# `running_jobs[].label_key` — 계약 A§12 · B§12 등재 키. 미등록 kind와 `COARSE_SEARCH`는 fallback.
JOB_LABEL_KEYS = {
    "PLATE_READ": "job.plate_read",
    "OVERLAY_TIME_READ": "job.overlay_time_read",
    "FINE_VERIFY": "job.fine_verify",
    "REPORT_VIDEO_EXPORT": "job.report_video_export",
    "PLATE_IMAGE_EXPORT": "job.plate_image_export",
    "HINT_EXTRACT": "job.hint_extract",  # v1.7 등재(#259, PR #286)
}
JOB_LABEL_FALLBACK = "job.generic_processing"


def derive_running_jobs(
    case: CaseAggregate, job_executions: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """case가 아직 결과를 기다리는 job(B§10 불변조건 5) = 정산되지 않은 JobRecord. status는 그 job의
    대표 execution(`attempt` 최댓값, A§10-6)이 없거나 `QUEUED`면 `PENDING`, 그 밖은 `RUNNING`이다 —
    terminal인데 아직 반영 전이거나 retry backoff 중이어도 case는 기다리는 중이다."""
    running = []
    for record in case.waiting_job_records():
        attempts = [e for e in job_executions or [] if e["job_id"] == record["job_id"]]
        status = max(attempts, key=lambda e: e["attempt"])["status"] if attempts else None
        running.append(
            {
                "job_id": record["job_id"],
                "kind": record["kind"],
                "label_key": JOB_LABEL_KEYS.get(record["kind"], JOB_LABEL_FALLBACK),
                "status": "PENDING" if status in (None, "QUEUED") else "RUNNING",
            }
        )
    return running


def representative_execution_status(
    job_records: list[dict[str, Any]], job_executions: list[dict[str, Any]], kind: str
) -> str | None:
    """`kind`의 대표 `JobExecution.status`. 대표 job은 그 kind로 `job_records[]`에 가장 나중에
    기록된 job이고(A§10-7 — `case_rev`는 정렬 키가 아니다), 그 안의 대표 execution은 `attempt`
    최댓값이다(A§10-6 — 재시도 중 이전 attempt의 STALE을 보이지 않는다). 그 kind의 job이 없거나
    대표 job에 아직 실행 보고가 없으면 `None` — 이전 job의 상태로 대신하지 않는다."""
    job_id = next((j["job_id"] for j in reversed(job_records) if j["kind"] == kind), None)
    attempts = [e for e in job_executions if e["job_id"] == job_id]
    if not attempts:
        return None
    return max(attempts, key=lambda e: e["attempt"])["status"]


def _job_execution_status_to_progress_state(status: str | None) -> str:
    """`status`가 `None`이면 "이 kind의 Job은 발주됐지만 아직 어떤 실행 결과도 case에
    보고되지 않았다"는 뜻이다(막 발주한 직후) — 낙관적으로 진행 중임을 보여준다(RUNNING).
    `scenario_infra_failure_001`의 rev1(plate_read 발주 직후, 아직 실행 결과 없음)로 확인."""
    if status is None:
        return "RUNNING"
    return _JOB_EXECUTION_STATUS_TO_PROGRESS_STATE[status]


def execution_failed(status: str | None) -> bool:
    """대표 실행이 terminal 실패인가 — B§13 매핑에서 `FAILED`가 되는 값(`FAILED` · 재시도가 끝난
    `STALE`). 보고가 없으면(`None`) 실패가 아니다."""
    return status is not None and _JOB_EXECUTION_STATUS_TO_PROGRESS_STATE[status] == "FAILED"


def _observed_state(status: str | None) -> str:
    """이미 끝난 관찰 단계 — 실행 상태가 보고됐으면(판독 실패 등) 그 값, 아니면 DONE이다.
    `_job_execution_status_to_progress_state()`와 달리 None을 「막 발주함」으로 읽지 않는다."""
    return "DONE" if status is None else _job_execution_status_to_progress_state(status)


def _build_progress(
    case: CaseAggregate,
    evidence_record: dict[str, Any] | None,
    report_package: dict[str, Any] | None,
    requirement_report_evidence: dict[str, Any] | None = None,
    *,
    plate_read_status: str | None = None,
    overlay_time_read_status: str | None = None,
    visual_evidence_decision: str | None = None,
    visual_verify_status: str | None = None,
) -> list[dict[str, str]]:
    # ⚠️ CANDIDATE_REVIEW 단계면 후보가 있든 없든(2026-09-14 확인 — 처음엔 "후보 0개"만의
    # 특수 케이스로 좁게 봤었는데, `scenario_relative_rebase_001`이 후보가 1개 있고 심지어
    # `selected:true`인 상태에서도 이후 단계(plate_read~package_assembly)로 진행될 경로가
    # 아직 없는 걸 보여줬다 — evidence 파이프라인은 `select_candidate()`로 stage가
    # EVIDENCE_REVIEW로 실제 전이돼야 시작되고, "화면에 selected로 표시된 후보가 있다"는
    # 것과 "stage가 전이됐다"는 건 별개다) 이후 단계로 진행될 경로 자체가 없다 —
    # 낙관적으로 PENDING을 보여주지 않고 목록에서 아예 뺀다. 검색·후보검토 자체는 정상
    # 완료된 것이므로(AnalysisRun.outcome=SUCCEEDED) candidate_review도 RUNNING이 아니라
    # DONE으로 표시한다(fixture로 검증됨, 2026-09-14).
    if case.stage == "CANDIDATE_REVIEW":
        return [
            {"step": "file_intake", "state": "DONE"},
            {"step": "coarse_search", "state": "DONE"},
            {"step": "candidate_review", "state": "DONE"},
        ]

    # ⚠️ EVIDENCE_REVIEW인데 evidence가 끝내 조립되지 못한 채(예: 번호판 판독이 인프라
    # 오류로 실패·취소를 거듭함) 머물러 있으면, plate_read/overlay_time_read는 각 Job의
    # 실행 상태(JobExecution.status projection)로 독립적으로 보여주고, 그 뒤 단계
    # (evidence_assembly~package_assembly)는 계산할 신뢰 가능한 신호 자체가 없으므로
    # 목록에서 아예 뺀다(CANDIDATE_REVIEW-빈 배열과 같은 원칙). `scenario_infra_failure_001`
    # 4개 revision 전부(plate_read가 RUNNING/FAILED/PARTIAL을 오가는 동안 overlay_time_read는
    # 독립적으로 DONE일 수 있다는 것까지) 이 분기로 확인됨(2026-09-14).
    # evidence가 없는 이유를 Fine 판정이 알려 주면 그것을 먼저 본다(PR #224 리뷰). 판정이 없으면
    # 아래 「조립 전」 분기 그대로다.
    # - 음성 결과(`NOT_ASSEMBLED`)는 IncidentClip~package를 시작하지 않는다(#168 [A]) — 뒤 단계는
    #   이 case 생애주기에서 일어날 계획이 없어 step 집합 규칙 3(`candidates=[]`와 같은 취급)으로 뺀다.
    #   빼지 않으면 판독 실행 상태가 보고되지 않아 RUNNING으로 보인다. Fine **실행 실패**(8-14)도
    #   판정 없이 같은 이유로 뒤 단계를 시작하지 않아 같은 3단계다.
    # - 상황 응답 대기(`AWAIT_SITUATION_RESPONSE`)는 관찰(OCR·시간 source)을 마쳤고 조립만 응답을
    #   기다린다(#165). 응답 뒤 package까지 이어지므로 규칙 1대로 8단계를 싣고, 조립 이후는 PENDING이다.
    if (
        case.stage == "EVIDENCE_REVIEW"
        and evidence_record is None
        and (visual_evidence_decision == NOT_ASSEMBLED or execution_failed(visual_verify_status))
    ):
        return [
            {"step": "file_intake", "state": "DONE"},
            {"step": "coarse_search", "state": "DONE"},
            {"step": "candidate_review", "state": "DONE"},
        ]
    if (
        case.stage == "EVIDENCE_REVIEW"
        and evidence_record is None
        and visual_evidence_decision == AWAIT_SITUATION_RESPONSE
    ):
        return [
            {"step": "file_intake", "state": "DONE"},
            {"step": "coarse_search", "state": "DONE"},
            {"step": "candidate_review", "state": "DONE"},
            {"step": "plate_read", "state": _observed_state(plate_read_status)},
            {"step": "overlay_time_read", "state": _observed_state(overlay_time_read_status)},
            {"step": "evidence_assembly", "state": "PENDING"},
            {"step": "requirement_check", "state": "PENDING"},
            {"step": "package_assembly", "state": "PENDING"},
        ]

    if case.stage == "EVIDENCE_REVIEW" and evidence_record is None:
        return [
            {"step": "file_intake", "state": "DONE"},
            {"step": "coarse_search", "state": "DONE"},
            {"step": "candidate_review", "state": "DONE"},
            {"step": "plate_read", "state": _job_execution_status_to_progress_state(plate_read_status)},
            {"step": "overlay_time_read", "state": _job_execution_status_to_progress_state(overlay_time_read_status)},
        ]

    # ⚠️ READY인데 evidence_record가 없으면(Fine이 NOT_ASSEMBLED로 분류해 IncidentClip~
    # package_assembly를 애초에 시작하지 않은 정상 종료, 이슈 #137과 같은 원칙) 위
    # EVIDENCE_REVIEW 분기와 동일하게 취급한다 — 아래 stage_rank 일반 로직은 READY를
    # "evidence_record가 있는 상태"로 암묵 가정해 8단계를 전부 DONE으로 덮어쓰므로,
    # 이 경우를 먼저 걸러내지 않으면 실행되지 않은 단계가 DONE으로 표시된다
    # (real_e2e_yt0002 실행에서 발견, 2026-09-23).
    if case.stage == "READY" and evidence_record is None:
        return [
            {"step": "file_intake", "state": "DONE"},
            {"step": "coarse_search", "state": "DONE"},
            {"step": "candidate_review", "state": "DONE"},
        ]

    stage = case.stage
    stage_rank = {"INTAKE": 0, "SEARCHING": 1, "CANDIDATE_REVIEW": 2, "EVIDENCE_REVIEW": 3, "READY": 4}[stage]

    def state_for(step_rank: int) -> str:
        if stage_rank > step_rank:
            return "DONE"
        if stage_rank == step_rank:
            return "RUNNING"
        return "PENDING"

    # step_rank: file_intake=0(분석 시작으로 INTAKE를 벗어나면 DONE — 원본은 파일마다 따로 들어와 「다 올렸다」는
    # 분석 시작으로만 안다, `decisions/empty-case-and-manifest.md`), coarse_search=1, candidate_review=2,
    # plate_read/overlay_time_read/evidence_assembly=3(EVIDENCE_REVIEW 진행), requirement_check/
    # package_assembly=3.5(EVIDENCE_REVIEW 안에서도 evidence 이후 단계) — evidence_record/
    # report_package 존재 여부로 더 세분화한다.
    progress = {
        "file_intake": "DONE" if stage_rank >= 1 else "PENDING",
        "coarse_search": state_for(1),
        "candidate_review": state_for(2),
    }
    # 후보 탐색 Run이 실패했으면 진행 중(RUNNING)으로 보이지 않게 한다 — 「결과 없음」과도,
    # 「아직 찾는 중」과도 다른 상태다(PR #187 리뷰).
    if case.candidate_search_failed:
        progress["coarse_search"] = "FAILED"
    if stage_rank < 3:
        for step in ("plate_read", "overlay_time_read", "evidence_assembly", "requirement_check", "package_assembly"):
            progress[step] = "PENDING"
    else:
        evidence_done = evidence_record is not None
        package_done = report_package is not None
        for step in ("plate_read", "overlay_time_read", "evidence_assembly"):
            if evidence_done:
                progress[step] = "DONE"
            elif stage_rank == 3:
                progress[step] = "RUNNING"
            else:
                progress[step] = "PENDING"
        # 번호판 판독이 실행 실패여도 evidence는 번호판 없이 조립된다 — evidence가 있다는 이유로
        # plate_read를 DONE으로 덮으면 실행 실패(4a)가 「읽지 못함」(1·3)과 구분되지 않는다
        # (#172 [D]). 실행 상태가 보고됐으면 그 값을 쓴다.
        if plate_read_status is not None:
            progress["plate_read"] = _job_execution_status_to_progress_state(plate_read_status)
        # ⚠️ requirement_check은 package_assembly와 별개 게이트다(`scenario_plate_reread_001`로
        # 확인 — requirements_evidence가 이미 존재해도 report_package는 아예 발주 안 될 수 있다).
        # package_assembly는 신뢰 가능한 "생성 중" 신호가 없어 낙관적으로 RUNNING을 보여주지 않는다
        # (report_package가 생기기 전까지는 PENDING — fixture로 검증됨, 2026-09-14).
        requirement_done = requirement_report_evidence is not None
        if requirement_done:
            progress["requirement_check"] = "DONE"
        elif evidence_done and stage_rank == 3:
            progress["requirement_check"] = "RUNNING"
        else:
            progress["requirement_check"] = "PENDING"
        progress["package_assembly"] = "DONE" if package_done else "PENDING"
        # ⚠️ PM 리뷰(2026-09-23, PR #147) — 여기 있던 "stage_rank==4(READY)면 8단계
        # 전부 DONE으로 덮어쓴다"는 블랙킷 override를 제거한다. 바로 위에서 이미
        # evidence_done/package_done/requirement_done을 보고 단계별로 정확히
        # 계산해두는데, 이 override가 그 결과를 무시하고 package_assembly까지
        # 무조건 DONE으로 덮어써서 `report_package is None`(예: PackageNotReady로
        # BLOCKED)인 READY 상태에서도 package_assembly=DONE이라는 허위 표시가
        # 나왔다(`youtube_clip_01` 실행에서 실제로 재현됨). READY에서
        # evidence_record가 있는데 report_package가 없는 조합은 이제 바로 위
        # 코드가 이미 정확히 PENDING을 내므로, 이 override 없이도
        # file_intake/coarse_search/candidate_review는 항상 DONE(stage_rank
        # 비교로 자동 보장), plate_read~requirement_check는 evidence_done/
        # requirement_done 여부로 정확히 DONE이 된다 — 8단계 전부 DONE인 경우도
        # (예: happy path) 이 계산 결과로 이미 자연스럽게 나온다.
    return [{"step": s, "state": progress[s]} for s in _PROGRESS_STEPS]


def _build_candidates_view(
    case: CaseAggregate,
    evidence_record: dict[str, Any] | None,
    current_timeline_revision: int | None = None,
) -> list[dict[str, Any]]:
    # ⚠️ 2026-09-14 정정(`scenario_correction_rerun_001`로 확인, 이슈 #39 Required-3 재확인):
    # candidates[].at/at_provenance는 evidence가 확정돼도 occurred_at으로 덮어쓰지 않는다 —
    # candidate 재선택이 없는 한 timeline 위치가 바뀔 이유가 없다. 과거엔 evidence_record가
    # 있고 candidate가 selected면 occurred_at.value/source.kind로 덮어썼는데, 이건 correction
    # 적용 후(candidate 재선택 없이 occurred_at만 바뀐 상황)에도 at/at_provenance가 같이
    # 바뀌어버리는 회귀였다 — v5에서 이미 한 번 고쳤다가 다시 들어간 버그.
    #
    # `stale_revision`/`stale_revision_label_key`는 candidate 생성 시점에 고정해두는 값이
    # 아니라 "매 투영 시점"에 다시 비교해서 만드는 파생값이다(`candidate-stale-revision-
    # display.md` 결정문 그대로: "case가 매 투영 시점에 비교해 계산하는 파생값") —
    # `current_timeline_revision`(그 candidate가 속한 `RecordingTimeline`의 **현재**
    # revision, recording이 소유)이 주어지면 `c.timeline_revision`과 비교해서 다시 계산하고,
    # 주어지지 않으면(대부분의 다른 시나리오 — 전부 단일 revision만 쓴다) Candidate에 이미
    # 저장된 값을 그대로 쓴다(하위 호환). `scenario_relative_rebase_001`의 rev1(rebase 전,
    # current_timeline_revision=1=timeline_revision → stale_revision:false)→rev2(rebase 후,
    # current_timeline_revision=2≠timeline_revision:1 → stale_revision:true,
    # stale_revision_label_key:"candidate.stale_timeline_revision")로 확인.
    out = []
    # rank 오름차순(#122). rank가 없는 후보(구 fixture 등)는 뒤로, 같은 rank면 받은 순서를 유지한다.
    for c in sorted(case.candidates, key=lambda c: (c.rank is None, c.rank or 0)):
        at, at_provenance = c.at, c.at_provenance
        situation_confirmation = c.situation_confirmation
        if current_timeline_revision is None:
            stale_revision = c.stale_revision
            stale_revision_label_key = c.stale_revision_label_key
        else:
            stale_revision = c.timeline_revision != current_timeline_revision
            stale_revision_label_key = "candidate.stale_timeline_revision" if stale_revision else None
        # candidates[].situation_confirmation — B절 §6 필드 정의: EvidenceRecord.situation_response.value가
        # 있으면 그대로 옮기고(CONFIRMED/CORRECTED/USER_UNSURE), 없으면 기존 NOT_ASKED를 유지한다.
        if evidence_record is not None and c.selected:
            situation_response = evidence_record.get("situation_response")
            if situation_response is not None:
                situation_confirmation = situation_response["value"]
        out.append(
            {
                "candidate_id": c.candidate_id,
                "rank": c.rank,
                # 시간축 마커(#184). stale 후보는 rebase 후 좌표 보장이 확인되기 전까지 null.
                "marker_ms": None if stale_revision else c.representative_ms,
                "at": at,
                "at_provenance": at_provenance,
                "at_provenance_label_key": at_provenance_label_key(at_provenance),
                "observed": c.observed,
                "thumb_ref": c.thumb_ref,
                "selected": c.selected,
                "timeline_revision": c.timeline_revision,
                "stale_revision": stale_revision,
                "stale_revision_label_key": stale_revision_label_key,
                "situation_confirmation": situation_confirmation,
            }
        )
    return out


def _field_states(evidence_record: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    """B절 §7-(1)/(2)/(3) 파생 규칙 — `report_fields`/`report_field_states`(§10 불변조건 13)와
    `evidence.*_display`가 공유하는 5개 필드(case_type 제외)의 info_state를 여기서 만든다.

    `evidence_record`는 EvidenceRecord이거나, 상황 응답 대기 중의 상황 독립 값(evidence
    `resolve_independent_facts()` 결과 — `event` 없음, #239)이다. `event`가 없으면 상황 종속 두 필드는
    `INFO_UNKNOWN`이다(값을 임의로 확정하지 않는다)."""
    event = evidence_record.get("event")
    # ⚠️ occurred_at도 vehicle_number/location과 같은 이유로 키 자체가 없을 수 있다
    # (TimeResolution.status=UNKNOWN이면 assemble_evidence()가 occurred_at을 아예 안 만든다
    # — evidence/assembly.py:230-231). 실제 real 영상(시간 출처가 전혀 없는 화면녹화본)에서
    # 처음 발생 확인, 2026-09-23. `occurred_at_info_state(None)`은 이미 "INFO_UNKNOWN"을
    # 반환하도록 되어 있었다 — 여기서 `.get()`으로 안 바꾼 게 유일한 gap이었다.
    occurred_at = evidence_record.get("occurred_at")
    # ⚠️ vehicle_number도 location처럼 키 자체가 없을 수 있다(번호판 판독 abstain —
    # `scenario_plate_reread_001`의 `ev_p001`, 2026-09-14 확인된 결함. 과거엔
    # `evidence_record["vehicle_number"]`가 KeyError를 던졌다).
    vehicle_number = evidence_record.get("vehicle_number")
    # ⚠️ location은 EvidenceRecord에 키 자체가 없을 수 있다(예: scenario_unknown_abstain_partial_001의
    # ev_u001 — 위치를 확보하지 못한 사건). 이슈 #48 Q2 조사에서 확인된 실제 결함 — `.get()`으로
    # None-safe하게 처리한다(과거에는 `evidence_record["location"]`이 KeyError를 던졌다).
    location = evidence_record.get("location")
    location_value, location_key = location_representative(location)

    if location_value is None:
        location_info_state = "INFO_UNKNOWN"
    elif location_key == "user_hint":
        # B절 §7-(3) 고정 규칙: 대표값이 user_hint면 info_state는 항상 INFO_NEEDS_REVIEW다
        # (rule (1)의 일반 우선순위를 타지 않는 예외 — user_corrected=true인 fixture에서도
        # INFO_USER_CONFIRMED로 올라가지 않는다. scenario_happy_001로 검증됨).
        location_info_state = "INFO_NEEDS_REVIEW"
    else:
        location_info_state = evidence_value_info_state(
            location_value.get("value"),
            needs_review=location_value.get("needs_review", False),
            user_corrected=location_value.get("user_corrected", False),
            observability=location_value["source"].get("observability"),
        )

    return {
        "vehicle_number": {
            "info_state": (
                evidence_value_info_state(
                    vehicle_number["value"],
                    needs_review=vehicle_number["needs_review"],
                    user_corrected=vehicle_number["user_corrected"],
                    observability=vehicle_number["source"].get("observability"),
                )
                if vehicle_number is not None
                else "INFO_UNKNOWN"
            ),
            "source_label_key": vehicle_number["source"]["label_key"] if vehicle_number is not None else None,
        },
        "occurred_at": {
            "info_state": occurred_at_info_state(occurred_at),
            "source_label_key": occurred_at["source"]["label_key"] if occurred_at is not None else None,
        },
        "location": {
            "info_state": location_info_state,
            "source_label_key": location_value["source"]["label_key"] if location_value is not None else None,
        },
        "violation_expression": _event_field_state(event, "violation_expression"),
        "safety_report_type": _event_field_state(event, "safety_report_type"),
    }


def _event_field_state(event: dict[str, Any] | None, field: str) -> dict[str, str | None]:
    if event is None:
        return {"info_state": "INFO_UNKNOWN", "source_label_key": None}
    value = event[field]
    return {
        "info_state": evidence_value_info_state(
            value["value"],
            needs_review=value["needs_review"],
            user_corrected=value["user_corrected"],
            observability=value["source"].get("observability"),
        ),
        "source_label_key": value["source"]["label_key"],
    }


# 상황 응답 전 부분 투영(#239)에서 상황 종속 세 필드의 모양 — 값 없음 + `INFO_UNKNOWN`. 새 enum 값은 만들지 않는다.
_SITUATION_PENDING_DISPLAY: dict[str, Any] = {
    "code": None,
    "label": None,
    "needs_review": False,
    "info_state": "INFO_UNKNOWN",
    "source_label_key": None,
}


def _build_evidence_view(
    evidence_record: dict[str, Any],
    preview_ref: str | None,
    user_edited: bool,
    plate_preview_ref: str | None = None,
) -> dict[str, Any]:
    # ⚠️ 2026-09-14 확인(`scenario_correction_rerun_001`): evidence.user_edited은 record 내부
    # 개별 필드의 user_corrected를 OR로 묶은 게 아니다 — `scenario_happy_001`의
    # location.user_hint는 user_corrected=true지만 evidence.user_edited=false다(user_hint는
    # 애초에 사용자가 준 값이라 "정정"이 아니다). 실제로는 case가 소유하는 CorrectionRecord가
    # 하나라도 있는지(`bool(case.correction_records)`)로 판정한다 — correction 전(false)/
    # 후(true) fixture와 정확히 일치한다. 호출부(`build_case_view`)에서 계산해 넘겨준다.
    #
    # 상황 응답 대기의 부분 투영(#239)이면 `evidence_record`는 상황 독립 값만 담은 evidence
    # `resolve_independent_facts()` 결과다 — `record_ref` · `event`가 없다. 그때 `record_id=null`, 상황 종속
    # 세 display는 `_SITUATION_PENDING_DISPLAY`이고, 나머지 값 · `review_needed`는 아래 같은 규칙으로 만든다.
    event = evidence_record.get("event")
    states = _field_states(evidence_record)
    # ⚠️ location 키 자체가 없는 EvidenceRecord가 정상 케이스다(위치 미확보 — 이슈 #48).
    # 아래 location_display 구성도 이에 맞춰 None-safe해야 한다.
    location = evidence_record.get("location")
    location_value, _location_key = location_representative(location)

    vehicle_number = evidence_record.get("vehicle_number")
    # ⚠️ occurred_at도 vehicle_number/location과 같은 이유로 키 자체가 없을 수 있다
    # (TimeResolution.status=UNKNOWN — evidence/assembly.py:230-231). 실제 real 영상(시간
    # 출처가 전혀 없는 화면녹화본)에서 처음 발생 확인, 2026-09-23.
    occurred_at = evidence_record.get("occurred_at")

    if event is None:
        case_type_display = dict(_SITUATION_PENDING_DISPLAY)
        report_type_display = dict(_SITUATION_PENDING_DISPLAY)
        violation_display = dict(_SITUATION_PENDING_DISPLAY)
    else:
        case_type = event["visual_event_type"]
        report_type = event["safety_report_type"]
        violation = event["violation_expression"]
        case_type_display = {
            "code": case_type["value"],
            "label": event_type_label(case_type["value"]),
            "needs_review": case_type["needs_review"],
            "info_state": evidence_value_info_state(
                case_type["value"],
                needs_review=case_type["needs_review"],
                user_corrected=case_type["user_corrected"],
                observability=case_type["source"].get("observability"),
            ),
            "source_label_key": case_type["source"]["label_key"],
        }
        report_type_display = {
            "code": report_type["value"],
            "label": report_type_label(report_type["value"]),
            "needs_review": report_type["needs_review"],
            "info_state": states["safety_report_type"]["info_state"],
            "source_label_key": report_type["source"]["label_key"],
        }
        violation_display = {
            "code": None,
            "label": violation["value"],
            "needs_review": violation["needs_review"],
            "info_state": states["violation_expression"]["info_state"],
            "source_label_key": violation["source"]["label_key"],
        }
    event_time_needs_review = (
        occurred_at.get("resolution_status") == "NEEDS_REVIEW" if occurred_at is not None else False
    )
    location_needs_review = location_value.get("needs_review", False) if location_value is not None else False

    # review_needed(object-level) 파생 — B절 §7 "evidence.review_needed 파생 규칙"(2026-09-09,
    # 개정 2026-09-10 이슈 #26 B-web-6): 6개 *_display 각각의 needs_review OR info_state==INFO_NEEDS_REVIEW.
    # reason_code는 원인이 한 필드면 evidence.<field>_needs_review, 둘 이상이면
    # evidence.multiple_fields_need_review(원인이 없으면 null).
    review_fields: dict[str, tuple[bool, str]] = {
        "case_type": (case_type_display["needs_review"], case_type_display["info_state"]),
        "report_type": (report_type_display["needs_review"], report_type_display["info_state"]),
        "violation": (violation_display["needs_review"], violation_display["info_state"]),
        "plate": (
            vehicle_number["needs_review"] if vehicle_number is not None else False,
            states["vehicle_number"]["info_state"],
        ),
        "event_time": (event_time_needs_review, states["occurred_at"]["info_state"]),
        "location": (location_needs_review, states["location"]["info_state"]),
    }
    triggered = [name for name, (nr, info) in review_fields.items() if nr or info == "INFO_NEEDS_REVIEW"]
    review_needed = bool(triggered)
    if not triggered:
        reason_code = None
    elif len(triggered) == 1:
        reason_code = f"evidence.{triggered[0]}_needs_review"
    else:
        reason_code = "evidence.multiple_fields_need_review"

    return {
        "record_id": (evidence_record.get("record_ref") or {}).get("ref"),
        "case_type_display": case_type_display,
        "report_type_display": report_type_display,
        "violation_display": violation_display,
        "plate_display": {
            "value": vehicle_number["value"] if vehicle_number is not None else None,
            "needs_review": vehicle_number["needs_review"] if vehicle_number is not None else False,
            "info_state": states["vehicle_number"]["info_state"],
            "source_label_key": vehicle_number["source"]["label_key"] if vehicle_number is not None else None,
        },
        "event_time_display": {
            # ⚠️ occurred_at 미확보(키 없음, TimeResolution.status=UNKNOWN)는 location_display와
            # 같은 원칙(§19 "제품 안에서 완결되지 않는 게 정상") — 실패로 표시하지 않고 값 자체가
            # 없다는 것을 그대로 나타낸다.
            "value": occurred_at["value"] if occurred_at is not None else None,
            # ⚠️ 과거엔 False로 고정돼 있었다 — B절 §7-(2): "event_time_display.needs_review는
            # resolution_status == NEEDS_REVIEW를 그대로 옮긴다."
            "needs_review": event_time_needs_review,
            "info_state": states["occurred_at"]["info_state"],
            "source_label_key": occurred_at["source"]["label_key"] if occurred_at is not None else None,
        },
        "location_display": (
            {
                "value": location_value["value"],
                # ⚠️ 필드 자체의 needs_review는 대표값(location_value)의 원본을 그대로 옮긴다 — "검토 필요"
                # 신호는 info_state(INFO_NEEDS_REVIEW)와 evidence.review_needed(object-level)로 표현된다.
                "needs_review": location_value.get("needs_review", False),
                "info_state": states["location"]["info_state"],
                "source_label_key": location_value["source"]["label_key"],
                # coord/search_keyword는 대표값 후보가 아니라 항상 별도로 내려보낸다(B절 §7-(3)) —
                # 둘 다 optional 키라 location 자체가 있어도 없을 수 있다(.get()으로 방어).
                "coord": (location.get("coord") or {}).get("value") if location else None,
                "search_keyword": (location.get("search_keyword") or {}).get("value") if location else None,
            }
            if location_value is not None
            # ⚠️ 위치 미확보(location 키 없음, 또는 address/place_name/user_hint 전부 없음) — §19
            # 원칙("제품 안에서 완결되지 않는 게 정상")에 따라 실패로 표시하지 않고, "값 자체가
            # 없다"를 그대로 나타낸다. 고칠 수 있는 in-app 액션이 없으므로 needs_review=False.
            else {
                "value": None,
                "needs_review": False,
                "info_state": states["location"]["info_state"],
                "source_label_key": None,
                "coord": None,
                "search_keyword": None,
            }
        ),
        "user_edited": user_edited,
        "preview_ref": preview_ref,
        "plate_preview_ref": plate_preview_ref,
        "review_needed": review_needed,
        "reason_code": reason_code,
    }


def _plate_preview_ref(
    evidence_record: dict[str, Any], plate_readouts: list[dict[str, Any]] | None
) -> str | None:
    """`evidence.plate_preview_ref`(#47) — 현재 번호판 값의 근거 PlateReadout의 `best_frame.frame_ref`.

    근거 PlateReadout은 `vehicle_number.source.ref` → `support_refs` 순서로 처음 나오는
    `kind=plate_readout` ref다(evidence가 준 연결을 그대로 따른다 — case가 판독을 고르지 않는다).
    재판독 뒤에는 재판독 결과를 가리키므로 첫 판독 프레임이 남지 않는다. 번호판 값이 없거나
    (판독 abstain) PlateReadout 근거가 없으면 `None`. `crop_ref`는 opaque identity라 내리지 않는다
    (`contract-plate-overlay-readout.md` §3·§9).
    """
    vehicle_number = evidence_record.get("vehicle_number") or {}
    refs = [(vehicle_number.get("source") or {}).get("ref") or {}, *(vehicle_number.get("support_refs") or [])]
    readout_id = next((r.get("ref") for r in refs if r.get("kind") == "plate_readout"), None)
    if readout_id is None:
        return None
    readout = next((p for p in plate_readouts or [] if p.get("readout_id") == readout_id), None)
    best_frame = (readout or {}).get("best_frame") or {}
    return best_frame.get("frame_ref")


def _build_requirements_view(requirement_report: dict[str, Any] | None) -> dict[str, Any] | None:
    if requirement_report is None:
        return None
    return {
        "readiness": requirement_report["overall"],
        "checks": requirement_report["checks"],
    }


def _build_package_view(report_package: dict[str, Any] | None, evidence_record: dict[str, Any] | None) -> dict[str, Any] | None:
    if report_package is None or evidence_record is None:
        return None
    states = _field_states(evidence_record)
    report_inputs = report_package["report_inputs"]
    report_fields = {}
    for field_name in _REPORT_FIELDS:
        value = report_inputs[field_name]
        if field_name == "location":
            # ⚠️ 위치를 확보하지 못한 사건은 report_inputs.location 자체가 null이다
            # (scenario_unknown_abstain_partial_001의 pkg_u001 — 이슈 #48). 예전에는
            # `value["display_text"]`가 TypeError를 던졌다.
            value = value["display_text"] if value is not None else None
        report_fields[field_name] = value
    field_states = {name: states[name] for name in _REPORT_FIELDS}
    unconfirmed = [name for name in _REPORT_FIELDS if field_states[name]["info_state"] != "INFO_SOURCE_VERIFIED"]
    return {
        "package_ref": report_package["package_ref"]["ref"],
        "report_fields": report_fields,
        "report_field_states": field_states,
        "artifact_ref": report_package["assets"]["report_video_ref"]["ref"],
        "capabilities": report_package["handoff"]["supported_actions"],
        "warnings": [],
        "unconfirmed_fields": unconfirmed,
        # 최종 신고문(v1.7, #274) — evidence가 확정 값 + 고정 template로 만든 문장을 그대로 옮긴다.
        # case는 고치지 않고, 내부 provenance인 `template_ref`는 내리지 않는다.
        "report": {
            "title": report_package["report"]["title"],
            "description": report_package["report"]["description"],
        },
    }


def _belongs_to_current_selection(
    case: CaseAggregate, selected: Any, evidence_record: dict[str, Any]
) -> bool:
    """`EvidenceRecord`가 지금 선택된 candidate·selection context에서 조립된 것인가.
    둘 다 evidence 계약 필드(`basis.candidate_ref`·`selection_rev`)를 그대로 비교할 뿐 값을
    재해석하지 않는다. 같은 candidate라도 selection_rev가 다르면(A→B→A) 이전 context다."""
    if selected is None:
        return False
    candidate_ref = (evidence_record.get("basis") or {}).get("candidate_ref") or {}
    return (
        candidate_ref.get("ref") == selected.candidate_id
        and evidence_record.get("selection_rev") == case.selection_rev
    )


def build_case_view(
    case: CaseAggregate,
    *,
    evidence_record: dict[str, Any] | None = None,
    requirement_report_evidence: dict[str, Any] | None = None,
    requirement_report_package: dict[str, Any] | None = None,
    report_package: dict[str, Any] | None = None,
    job_executions: list[dict[str, Any]] | None = None,
    notices: list[dict[str, Any]] | None = None,
    plate_read_status: str | None = None,
    overlay_time_read_status: str | None = None,
    current_timeline_revision: int | None = None,
    plate_readouts: list[dict[str, Any]] | None = None,
    visual_evidence_decision: str | None = None,
    visual_verify_status: str | None = None,
    independent_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = next((c for c in case.candidates if c.selected), None)
    preview_ref = selected.thumb_ref if selected else None

    # 현재 선택 context의 evidence만 투영한다(#173 E-4 조건 1의 전제, W7 6.6순위). 재선택 직후
    # adapter가 아직 이전 선택의 evidence를 들고 있어도 그대로 내리지 않는다 — web은
    # `EVIDENCE_REVIEW`+`evidence=null`일 때만 진행 화면을 띄우므로, 이전 evidence가 내려가면 준비
    # 중인데도 결과 화면(「다른 후보 보기」 포함)이 뜬다. 그 evidence에서 나온 RequirementReport·
    # ReportPackage도 같이 뺀다.
    if evidence_record is not None and not _belongs_to_current_selection(case, selected, evidence_record):
        evidence_record = None
        requirement_report_evidence = None
        requirement_report_package = None
        report_package = None

    # 상황 응답 대기 부분 투영(#239) — Fine `UNCERTAIN` + 응답 전이라 EvidenceRecord가 없어도, evidence가
    # 계산한 상황 독립 값을 `evidence`에 `record_id=null`로 싣는다. requirements · package는 그대로 null이다.
    # `independent_facts`는 adapter가 현재 선택의 응답 대기 판정과 같은 묶음에서 준 값이다.
    evidence_source = evidence_record
    if (
        evidence_source is None
        and visual_evidence_decision == AWAIT_SITUATION_RESPONSE
        and independent_facts is not None
        and selected is not None
    ):
        evidence_source = independent_facts

    return {
        "contract": "CaseView",
        "contract_version": CONTRACT_VERSION,
        "case_id": case.case_id,
        "case_rev": case.case_rev,
        "stage": case.stage,
        "user_reviewed": case.user_reviewed,
        # 분석 시작 때 사용자가 적은 설명 원문(v1.7, #259) — 받은 그대로. 분석 시작 전에는 `null`.
        "description": case.description,
        "manifest_summary": case.manifest_summary,
        "hints": case.hints,
        "progress": _build_progress(
            case,
            evidence_record,
            report_package,
            requirement_report_evidence,
            plate_read_status=plate_read_status,
            overlay_time_read_status=overlay_time_read_status,
            visual_evidence_decision=visual_evidence_decision,
            visual_verify_status=visual_verify_status,
        ),
        "candidates": _build_candidates_view(case, evidence_record, current_timeline_revision),
        "evidence": (
            _build_evidence_view(
                evidence_source,
                preview_ref,
                bool(case.correction_records),
                _plate_preview_ref(evidence_source, plate_readouts),
            )
            if evidence_source is not None
            else None
        ),
        "requirements_evidence": _build_requirements_view(requirement_report_evidence),
        "requirements_package": _build_requirements_view(requirement_report_package),
        "package": _build_package_view(report_package, evidence_record),
        "running_jobs": derive_running_jobs(case, job_executions),
        "notices": notices or [],
    }
