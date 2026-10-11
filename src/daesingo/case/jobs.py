"""JobRecord(Job Intent) 발주 — case가 유일하게 소유하는 발주 의도.

핵심 규칙 (`contract-job-execution.md` 2026-09-13 명확화, `contract-job-record-case-view.md`
`RESUME_SEARCH` 행 신설분 그대로): 사용자의 새 Intent는 **항상 새 job_id**로 발주한다.
`RETRY_PLATE_READ`/`RETRY_SEARCH`/`RESUME_SEARCH`("이어서 찾기")도 전부 새 job_id다.
같은 job_id + attempt 증가는 자동 인프라 재시도(`STALE`)뿐이며, 그건 common/runtime의
책임이라 이 모듈에는 아예 그 분기가 없다 — `domain.CaseAggregate.next_job_id()` 참고.

`JobRecord`는 발주 의도만 담고 실행 상태(`JobExecution`)는 담지 않는다(append-only).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from daesingo.case.domain import CaseAggregate

CONTRACT_VERSION = "job-record/v1"

JOB_KINDS = frozenset(
    {
        "COARSE_SEARCH",
        "PLATE_READ",
        "OVERLAY_TIME_READ",
        "FINE_VERIFY",
        "REPORT_VIDEO_EXPORT",
        # 신고용 번호판 이미지 생성 발주(#47). 실행 capability는 recording 구현 대기.
        "PLATE_IMAGE_EXPORT",
        # 자연어 단서 구조화 발주(v1.7, #259). 발주 경로(`START_ANALYSIS`)는 case-command Draft §11 미결 뒤.
        "HINT_EXTRACT",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def issue_job(
    case: CaseAggregate,
    kind: str,
    *,
    scope_ref: str | None = None,
    input_fingerprint: str,
    force_rerun: bool = False,
) -> dict[str, Any]:
    if kind not in JOB_KINDS:
        raise ValueError(f"알 수 없는 JobRecord.kind: {kind!r} (등록된 kind: {sorted(JOB_KINDS)})")
    if force_rerun:
        # 사용자가 명시적으로 재요청한 Job(재판독/재검색 등)은 그 자체가 새 "요청 시점 케이스
        # 리비전"이다(§3-E) — `scenario_plate_reread_001` fixture로 확인(2026-09-14): 재판독을
        # 발주하는 시점에 case_rev가 오르고, 그 job_record.case_rev도 오른 값을 그대로 담는다.
        case.bump_revision()
    job_record: dict[str, Any] = {
        "contract": "JobRecord",
        "contract_version": CONTRACT_VERSION,
        "job_id": case.next_job_id(kind),
        "case_id": case.case_id,
        "case_rev": case.case_rev,
        "kind": kind,
        "scope_ref": scope_ref,
        "input_fingerprint": input_fingerprint,
        "force_rerun": force_rerun,
        "requested_at": _now(),
    }
    # 같은 kind · scope_ref의 기다리던 job은 이 job으로 대체된다 — 대표 job은 가장 나중 job이다(A§10-7).
    for prior in case.waiting_job_records():
        if prior["kind"] == kind and prior["scope_ref"] == scope_ref:
            case.settle_job(prior["job_id"], "SUPERSEDED")
    case.record_job(job_record)
    return job_record


def issue_coarse_search(
    case: CaseAggregate, *, scope_ref: str, input_fingerprint: str, scope: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`scope`를 주면 aggregate에 남긴다(#246 S-4) — 주지 않는 기존 호출(fixture · 스크립트)은 그대로 둔다."""
    if scope is not None:
        if scope["scope_id"] != scope_ref:
            raise ValueError(f"scope_ref와 scope_id가 다르다: {scope_ref!r} != {scope['scope_id']!r}")
        case.record_analysis_scope(scope)
    return issue_job(case, "COARSE_SEARCH", scope_ref=scope_ref, input_fingerprint=input_fingerprint)


def issue_plate_read(case: CaseAggregate, *, input_fingerprint: str, force_rerun: bool = False) -> dict[str, Any]:
    return issue_job(case, "PLATE_READ", input_fingerprint=input_fingerprint, force_rerun=force_rerun)


def issue_overlay_time_read(case: CaseAggregate, *, input_fingerprint: str) -> dict[str, Any]:
    return issue_job(case, "OVERLAY_TIME_READ", input_fingerprint=input_fingerprint)


def issue_fine_verify(case: CaseAggregate, *, input_fingerprint: str) -> dict[str, Any]:
    return issue_job(case, "FINE_VERIFY", input_fingerprint=input_fingerprint)


def issue_report_video_export(case: CaseAggregate, *, input_fingerprint: str) -> dict[str, Any]:
    return issue_job(case, "REPORT_VIDEO_EXPORT", input_fingerprint=input_fingerprint)


def issue_resume_search(case: CaseAggregate, *, scope_ref: str, input_fingerprint: str) -> dict[str, Any]:
    """"이어서 찾기" — CANCELLED 이후 재개. 2026-09-13 결정: 새 job_id(kind=COARSE_SEARCH,
    force_rerun=True)로 발주한다. 같은 job_id를 재사용하지 않는다."""
    return issue_job(
        case,
        "COARSE_SEARCH",
        scope_ref=scope_ref,
        input_fingerprint=input_fingerprint,
        force_rerun=True,
    )


def issue_plate_reread(case: CaseAggregate, *, input_fingerprint: str) -> dict[str, Any]:
    """`EvidenceNeeds.items`가 `PLATE_REREAD`를 요청했을 때의 자동 발주(force_rerun=True)."""
    return issue_job(case, "PLATE_READ", input_fingerprint=input_fingerprint, force_rerun=True)


def issue_overlay_time_reread(case: CaseAggregate, *, input_fingerprint: str) -> dict[str, Any]:
    """`EvidenceNeeds.items`가 `OVERLAY_TIME_OCR`를 요청했을 때의 자동 발주(force_rerun=True) —
    `issue_plate_reread()`와 대칭(`contract-evidence-record-needs.md` §8.2 kind 매핑:
    `OVERLAY_TIME_OCR → would_fill=OCCURRED_AT`)."""
    return issue_job(case, "OVERLAY_TIME_READ", input_fingerprint=input_fingerprint, force_rerun=True)


def latest_job_record(case: CaseAggregate, kind: str) -> dict[str, Any] | None:
    """같은 kind로 가장 나중에 발주된 `JobRecord` — 재시도·재판독은 이 입력(`input_fingerprint`·
    `scope_ref`)을 그대로 쓴다(case는 fingerprint를 계산하지 않는다). 없으면 None."""
    return next((j for j in reversed(case.job_records) if j["kind"] == kind), None)


_NEED_KIND_TO_SOURCE_JOB_KIND = {
    "PLATE_REREAD": "PLATE_READ",
    "OVERLAY_TIME_OCR": "OVERLAY_TIME_READ",
}


def issue_needed_jobs(case: CaseAggregate, evidence_needs: dict[str, Any]) -> list[dict[str, Any]]:
    """`EvidenceNeeds.items` → Job Intent 자동 매핑(`contract-evidence-record-needs.md` §8.1/§8.2,
    "case는 이 Need가 current revision 기준으로 유효하면 백그라운드 JobIntent를 자동 발주할 수
    있다"). v1 kind는 `OVERLAY_TIME_OCR`/`PLATE_REREAD` 둘 뿐이다(§8.2, 닫힌 집합).

    `input_fingerprint`는 case가 새로 계산하지 않는다 — 재판독은 "같은 입력을 다시 본다"는
    뜻이므로, 같은 kind로 이미 발주됐던 가장 최근 `JobRecord`의 fingerprint를 그대로 재사용한다
    (`scenario_plate_reread_001` fixture로 확인, 2026-09-14: `job_p001_plate`와
    `job_p001_plate_reread`의 `input_fingerprint`가 완전히 동일한 `"sha1:p001-plate-read-clip_p001"`).
    해당 kind로 발주된 적이 아직 없으면(비정상 상태 — Need는 이미 한 번 관찰을 시도했다는 뜻이라
    보통 발생하지 않는다) `ValueError`를 던진다 — 조용히 임의 fingerprint를 만들어내지 않는다.
    """
    issued: list[dict[str, Any]] = []
    for item in evidence_needs.get("items", []):
        kind = item["kind"]
        source_kind = _NEED_KIND_TO_SOURCE_JOB_KIND.get(kind)
        if source_kind is None:
            raise ValueError(f"알 수 없는 EvidenceNeeds item.kind: {kind!r}")
        prior = latest_job_record(case, source_kind)
        if prior is None:
            raise ValueError(
                f"{kind!r} Need를 처리할 원본 {source_kind!r} JobRecord가 없다 (case_id={case.case_id!r})"
            )
        if source_kind == "PLATE_READ":
            issued.append(issue_plate_reread(case, input_fingerprint=prior["input_fingerprint"]))
        else:
            issued.append(issue_overlay_time_reread(case, input_fingerprint=prior["input_fingerprint"]))
    return issued
