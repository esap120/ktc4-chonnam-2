"""CorrectionRecord 생성 — case가 소유(Producer)하는 사용자 정정 기록.

`selection_rev`는 "수정 횟수 카운터가 아니라 그 수정이 일어난 candidate 선택 context"다
(`contract-correction-record.md` §4, 이슈 #39 Required-3에서 실제로 이 버그가 났던
지점 — `docs/mock/02_mock_scenario_catalog.md`의 `scenario_correction_rerun_001` v4 노트
참고). 그래서 여기서는 correction 시점의 `case.selection_rev`를 그대로 스냅샷하고,
correction 자체는 selection_rev를 절대 증가시키지 않는다.

반면 `case_rev`는 오른다(§3-E "요청 시점 케이스 리비전") — 사용자의 정정 제출은 그 자체가
새 요청이다. `scenario_correction_rerun_001` fixture로 확인(2026-09-14): correction 전
`case_rev:2` → correction 후 `case_rev:3`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from daesingo.case.domain import CaseAggregate, InvalidTransition

CONTRACT_VERSION = "correction-record/v1.1"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# case가 스스로 정의한 non-evidence target_field 네임스페이스 중 후보에 묶이지 않는 것
# (`contract-correction-record.md` §6).
_CASE_SCOPED_TARGETS = frozenset({"hints", "candidate.selected_id"})


def apply_correction(
    case: CaseAggregate,
    *,
    kind: str,
    target_field: str,
    previous_value: Any,
    new_value: Any,
) -> dict[str, Any] | None:
    # 후보에 묶인 값(번호판·시각·신고 유형 등)은 후보를 고른 뒤에만 고칠 수 있다 — 상태 기계 설계
    # 초안 v1 §4(`CANDIDATE_REVIEW`: 「아직 선택 전」, `SEARCHING`: 조회만). 선택 context가 없는
    # 정정은 기록할 `selection_rev`도, 반영할 evidence도 없다. 거부는 아무것도 바꾸기 전에 한다(#166).
    # case 전체 값(`hints`·`candidate.selected_id`)은 각 호출자가 자기 허용 stage를 검사한다.
    if target_field not in _CASE_SCOPED_TARGETS and case.stage not in ("EVIDENCE_REVIEW", "READY"):
        raise InvalidTransition(f"{case.stage}에서는 {target_field}를 정정할 수 없다(후보 선택 전)")
    # 값이 실제로 바뀌지 않았으면 기록하지 않는다(correction-record §8-7, `edit_time_hint()`와 같은
    # 원칙) — 반환값 `None`, `case_rev`도 그대로. 기록하면 evidence가 조립할 때 거부하고, 기록은
    # 되돌리지 않으므로(§8-9) 그 case는 이후 CaseView를 만들 수 없게 된다.
    if previous_value == new_value:
        return None
    # 같은 target_field의 최신(=supersede 체인의 head) correction을 찾는다 — 순환 방지를 위해
    # "가장 최근에 추가된 것"만 후보로 삼는다(같은 target_field에 여러 개가 있어도 head는 하나).
    # 후보에 종속된 값(evidence 의미 경로)은 같은 선택 context 안에서만 잇는다(#173 E-1) — 새
    # 후보의 첫 정정이 이전 후보의 정정을 supersede하면 evidence의 chain 연속성 검사에 걸린다.
    # hints·candidate.selected_id처럼 case 전체에 걸린 값은 후보가 바뀌어도 잇는다.
    previous = next(
        (
            c for c in reversed(case.correction_records)
            if c["target_field"] == target_field
            and (target_field in _CASE_SCOPED_TARGETS or c["selection_rev"] == case.selection_rev)
        ),
        None,
    )
    record: dict[str, Any] = {
        "contract": "CorrectionRecord",
        "contract_version": CONTRACT_VERSION,
        "correction_id": f"corr_{case.case_id}_{uuid.uuid4().hex[:8]}",
        "case_id": case.case_id,
        "selection_rev": case.selection_rev,  # 스냅샷 — 이 호출로 증가시키지 않는다
        # correction-record/v1.1 §3 — `supersedes_ref: ContractRef{kind: correction_record} | null`.
        "supersedes_ref": (
            {"kind": "correction_record", "ref": previous["correction_id"]} if previous else None
        ),
        "kind": kind,
        "target_field": target_field,
        "previous_value": previous_value,
        "new_value": new_value,
        "corrected_at": _now(),
    }
    case.correction_records.append(record)
    if target_field not in _CASE_SCOPED_TARGETS:
        case.leave_ready()  # 값이 다시 조립된다 — PACKAGE_READY gate를 다시 봐야 한다
    case.bump_revision()  # 정정 제출 = 새 요청 → case_rev 상승(§3-E)
    return record


_HINT_FIELDS = frozenset({"time", "vehicle", "situation", "location"})


def edit_time_hint(case: CaseAggregate, hints_patch: dict[str, str | None]) -> dict[str, Any] | None:
    """`TIME_HINT_EDIT` — `docs/modules/case/doc-research/부분 재실행 정책 표 초안 v1...md`
    1행: 시간 단서 등 `hints`를 고치면 `SEARCHING`으로 역행하고 1차 탐색부터 다시 돈다.

    `hints_patch`는 `{time?, vehicle?, situation?, location?}`(표에 적힌 payload 그대로) 중
    바뀐 키만 담은 부분 patch다. `previous_value`/`new_value`는 그 변경분만(전체 hints 블롭이
    아니라)을 dict로 담는다 — case가 이 namespace(`target_field="hints"`)의 값 타입을 스스로
    정의할 수 있다(`contract-correction-record.md` §6: "case가 추가하는 non-evidence
    target_field 네임스페이스... 닫힌 목록 아님").

    변경이 하나도 없으면(모든 값이 기존과 동일) `CorrectionRecord`를 만들지 않고 역행도 하지
    않는다 — §8 lifecycle 불변조건 1 "무효/무변경 입력 미생성"과 동일 원칙. 반환값은 그 경우
    `None`이다.
    """
    unknown = set(hints_patch) - _HINT_FIELDS
    if unknown:
        raise ValueError(f"알 수 없는 hint 필드: {sorted(unknown)}")

    changed_previous: dict[str, Any] = {}
    changed_new: dict[str, Any] = {}
    for field_name, new_value in hints_patch.items():
        previous_value = case.hints.get(field_name)
        if previous_value == new_value:
            continue
        changed_previous[field_name] = previous_value
        changed_new[field_name] = new_value

    if not changed_new:
        return None

    case.check_regress_to_searching()  # 거부될 요청이면 아무것도 남기지 않는다(#166과 같은 원칙)
    record = apply_correction(
        case, kind="TIME_HINT_EDIT", target_field="hints",
        previous_value=changed_previous, new_value=changed_new,
    )
    case.hints.update(changed_new)
    case.regress_to_searching()
    return record


def reselect_candidate(case: CaseAggregate, candidate_id: str) -> dict[str, Any]:
    """`OTHER_CANDIDATE` — 표 2행: 이미 선택한 뒤(`EVIDENCE_REVIEW`) 다른 후보가 맞다고
    정정한다. `EVIDENCE_REVIEW`면 제자리, `READY`면 새 초안을 위해 `EVIDENCE_REVIEW`로 돌아가고
    (#173 E-4), `selected` 플래그를 옮긴다. `target_field="candidate.selected_id"`도 case가 스스로 정의한
    네임스페이스다(§6, 예시로 명시된 이름 그대로 재사용).
    """
    # 거부될 요청이면 CorrectionRecord를 남기기 전에 멈춘다(#166 — 기록 후 거부되면
    # case_rev·CorrectionRecord만 남아 실제 선택 상태와 어긋났다).
    case.check_reselect(candidate_id)
    previous_id = next((c.candidate_id for c in case.candidates if c.selected), None)
    record = apply_correction(
        case, kind="OTHER_CANDIDATE", target_field="candidate.selected_id",
        previous_value=previous_id, new_value=candidate_id,
    )
    case.reselect_candidate(candidate_id)
    return record
