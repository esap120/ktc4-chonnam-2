"""readout 공개 함수 2개 — `read_plate` · `read_overlay_time`.

다른 모듈은 이 두 함수만 부른다. 반환은 v4 §4-모듈3 ③ 그대로 **둘**이다.

    read_plate(request, target_hint=None)  -> ReadoutRun, PlateReadout | None
    read_overlay_time(request)             -> ReadoutRun, OverlayTimeReadout | None

`span`이 아니라 `request`인 이유 — v4가 적은 `span`은 `plate-readout/v1.2`에서 `input_ref.span_ref`가
삭제되면서 사라졌다. 사건 구간의 canonical reference는 `incident_clip_ref` 하나이고
(contract-plate-overlay-readout.md v1.2 머리말), `AssetSpan`만 받아 판독하는 경로는 만들지 않는다
(contract-analysis-source-derived.md §6.8).

## 이 파일이 소유하는 판정

association 반영 · crop identity 발급 · multi-frame consensus · abstain 사유 선택 ·
overlay 4갈래 · validation 3종 · `ReadoutRun` 조립. 임계값도 여기 있다 — 판정 임계값을
소비 쪽(web·evidence)에서 계산하지 않는다.

## 이 파일이 하지 않는 것

- **`JobExecution`·`CaseView`를 모른다.** 그것들로 감싸는 것은 worker의 일이다.
- **확정값을 만들지 않는다.** 여기서 나오는 것은 전부 관찰값이다(계약 §3-1).
- **`frame_ref`를 파싱하지 않는다.** 받은 그대로 보존한다(§3 `frame_ref` 형식).
- **`UsageRecord`를 발행하지 않는다.** `usage_refs`는 빈 배열로 두고, 발행에 필요한 「호출 사실과
  시간」은 `ReadoutRun.started_at`/`ended_at`으로 worker에 넘어간다. authoritative는
  `UsageRecord.run_ref`다(contract-usage-record.md §8-11).

## 실행 1회 = `ReadoutRun` 1건

두 함수 모두 실행하면 반드시 run 1건을 만든다. 결과 객체는 0~1건이다 — provider가 완전 실패하면
run만 남는다(contract-readout-run.md §5).

예외가 나가는 자리는 **하나뿐**이다 — 입력이 계약 형식이 아니면 provider를 부르기 전에
`ValueError`로 세운다. 그때는 판독이 시작되지 않았으므로 run도 없다. 반대로 provider를 부른
**뒤에** 발견한 문제(계약을 어긴 응답)는 예외로 되돌리지 않는다. 이미 실행이 일어났고 비용도
나갔으므로 `INFRA`/`READOUT_PIPELINE_ERROR` 실패 run으로 닫는다 — 그래야 worker가
`JobExecution.produced`와 `UsageRecord` 발행 근거를 잃지 않는다.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import NamedTuple, Optional

from . import providers, registry
from .contracts import (
    AssociatedRegion,
    AssociationEvidence,
    BestFrame,
    Consensus,
    ContractRef,
    Failure,
    FrameResult,
    InputRef,
    Observation,
    ObservationReason,
    OverlaySample,
    OverlayTimeReadout,
    OverlayValidation,
    PlateReadout,
    ProducedBy,
    ReadoutRun,
    TargetAssociation,
)

# ── 계약 버전 ────────────────────────────────────────────────
# 값의 원문은 계약 문서다. fixture가 쓰는 것과 같은 문자열을 쓴다.
READOUT_RUN_VERSION = "readout-run/v1"
PLATE_READOUT_VERSION = "plate-readout/v1.3"
OVERLAY_TIME_READOUT_VERSION = "overlay-time-readout/v1.2"
OBSERVATION_VERSION = "observation/v1"

MODULE = "readout"

# ── 판정 임계값 ──────────────────────────────────────────────
# 전부 잠정이다. 실측 뒤 readout Technical Spec에서 확정한다
# (decisions/overlay-presence-detection.md 미결 #3·#4와 같은 성격).

PLATE_ACCEPT_CONFIDENCE = 0.50
"""best frame OCR 신뢰도가 이 아래면 확정하지 않고 보류한다. 신뢰도는 보조 신호이므로
단독 확정 기준으로는 쓰지 않는다(계약 §4 핵심 원칙 5) — 보류 쪽으로만 쓴다."""

MIN_PLATE_PX_HEIGHT = 20
"""번호판 영역 높이(px) 하한. 이 아래면 문자 판독 자체가 성립하지 않는다고 본다."""

MIN_AGREEING_FRAMES = 3
"""프레임이 서로 다를 때, 같은 문자열을 읽은 프레임이 이 수 이상이고 과반이면 다수결로 합의한다.
2:1은 1표 차이라 합의로 보지 않는다. 실측(GT 13, 2026-09-28)에서 「투표 일치 + 프레임 ≥ 3」이
오답 확정을 0으로 만든 조건이다(`experiments/plate-ocr-ablation-2026-09-27/` §3-⑥)."""

FULL_PLATE = re.compile(r"\d{2,3}[가-힣]\d{4}|[가-힣]{2}\d{1,2}[가-힣]\d{4}")
"""온전한 번호판 형식 — 신형(`12가3456`·`123가4567`)과 지역명 포함(`서울12가3456`).
이 형식이 아닌 값은 번호판 전체가 아니라 글자 한 줄을 골라 온 것이라 보류한다."""

OVERLAY_QUANTIZATION_SEC = 1.0
"""overlay는 초 단위로 찍힌다. 어느 두 sample이든 이만큼은 어긋날 수 있다."""

OVERLAY_DRIFT_RATIO = 0.02
"""구간이 길수록 허용 오차도 커진다 — 위 양자화 오차에 이 비율만큼 더한다."""

OVERLAY_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y.%m.%d %H:%M:%S",
)
"""지원하는 overlay 날짜/시간 형식. 여기서 못 읽으면 `format_ok=false`다(계약 §7)."""

OVERLAY_TIME_IN_TEXT = re.compile(r"\d{4}[-/.]\d{2}[-/.]\d{2}[ T]\d{2}:\d{2}:\d{2}")
"""OCR 원문 **안에서** 시각 부분을 찾는 패턴. 위 형식들이 쓰는 구분자를 그대로 받는다.

여기서 찾은 문자열만 `OVERLAY_TIME_FORMATS`로 해석한다 — 이 패턴은 자리를 찾을 뿐이고
유효성은 `strptime`이 판정한다(`13/45/99 99:99:99`는 이 패턴을 통과하고 거기서 걸린다).
왜 원문 전체를 쓰지 않는지는 `_parse_overlay_text()`에 있다."""

TZ_OFFSET = re.compile(r"(?:[+-]\d{2}:\d{2}|Z)")
"""계약이 정한 `tz_offset` **표기**. overlay 문자열에는 timezone이 없어서 clip의 source
메타데이터에서 오는데, 그 값이 비어 있거나 ISO offset이 아니면 여기서 붙인 문자열이 시각이
아니게 된다.

표기만으로는 부족하다 — `+25:99`는 이 패턴을 통과하지만 시각이 아니다. 유효성 판정은
`_valid_tz_offset()`이 하고, 이 상수는 그 앞단의 표기 검사만 맡는다."""


# ── 입력 ─────────────────────────────────────────────────────

@dataclass
class TargetHint:
    """optional이다. 없어도 실행하고, 자체 association을 시도한다(v4 §4-모듈3 ③)."""
    track_ref: Optional[str] = None
    frame_ref: Optional[str] = None
    bbox_xywh: Optional[list] = None


@dataclass
class ReadRequest:
    """공개 함수의 입력. 계약 형식 그대로 받는다."""
    case_id: str
    candidate_id: str
    input_ref: InputRef
    usage_refs: list = field(default_factory=list)
    """worker가 이미 발행한 `UsageRecord` 참조가 있으면 넘길 수 있다. 기본은 빈 배열이다."""


class PlateReadResult(NamedTuple):
    run: ReadoutRun
    plate: Optional[PlateReadout]


class OverlayTimeReadResult(NamedTuple):
    run: ReadoutRun
    overlay: Optional[OverlayTimeReadout]


# ── 공통 조립 ────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    """1회성 식별자. `run_id`는 `execution_id`와 같은 identity가 아니다(계약 §5)."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _issue_crop_refs(frames) -> list:
    """프레임별 crop identity를 발급한다. `frames`와 같은 길이·순서의 목록을 준다.

    identity는 `(frame_ref, bbox, source_profile)`이다(계약 §3 「crop_ref identity」). 한 실행은
    `source_profile` 하나를 쓰므로 여기서 가르는 것은 **앞의 둘**이다 — 같은 프레임에서 영역을
    둘 떠서 읽으면 서로 다른 crop이고, 같은 프레임의 같은 영역이면 같은 crop이라
    `best_frame`과 `frame_results`가 그것을 나눠 쓴다.

    실행을 가로질러서는 재사용하지 않는다. 프레임을 다시 떠서 읽으면 새 `crop_ref`를 발급한다 —
    같은 프레임을 같은 profile로 다시 읽어도 그것은 새 추출이다.
    """
    issued = {}
    return [
        issued.setdefault((f.frame_ref, tuple(f.bbox_xywh)), _new_id("crop"))
        for f in frames
    ]


def _copy_input_ref(input_ref) -> InputRef:
    """결과 객체는 자기 `input_ref`를 갖는다 — 호출자가 뒤에 request를 고쳐도 흔들리지 않게.

    재판독은 같은 request의 `source_profile`만 바꿔 다시 부르는 모양이 자연스러운데, 그때
    앞 판독의 결과까지 따라 바뀌면 「기존 판독을 mutate하지 않는다」가 깨진다.
    """
    return InputRef(
        incident_clip_ref=input_ref.incident_clip_ref,
        source_profile=input_ref.source_profile,
        provenance=input_ref.provenance,
    )


def _provider_broke_contract(detail: str) -> "providers.ProviderError":
    """provider를 부른 뒤에 발견한 계약 위반. 예외로 되돌리지 않고 실패 run으로 닫는다."""
    return providers.ProviderError("INFRA", "READOUT_PIPELINE_ERROR", detail)


def _validate_input_ref(input_ref) -> None:
    if not isinstance(input_ref, InputRef):
        raise ValueError("input_ref는 계약 형식(InputRef)이어야 한다")
    if not input_ref.incident_clip_ref:
        raise ValueError("incident_clip_ref는 필수다 — 사건 구간 canonical reference다")
    if input_ref.source_profile not in registry.SOURCE_PROFILES:
        raise ValueError(
            f"등재되지 않은 source_profile이다: {input_ref.source_profile!r} — "
            "계약 §3에 등재한 뒤 쓴다"
        )
    if input_ref.provenance not in registry.PROVENANCES:
        raise ValueError(
            f"등재되지 않은 provenance다: {input_ref.provenance!r} — "
            "OCR 근거는 Source-derived여야 한다(계약 §3-2·§3-3)"
        )


def _start_run(operation: str, request) -> ReadoutRun:
    return ReadoutRun(
        run_id=_new_id("rr"),
        operation=operation,
        outcome="SUCCEEDED",
        failure=None,
        usage_refs=list(request.usage_refs),
        started_at=_now(),
        ended_at=None,
        contract="ReadoutRun",
        contract_version=READOUT_RUN_VERSION,
    )


RUN_FAILURE_KIND = "INFRA"
"""`outcome=FAILED`로 run을 닫을 수 있는 유일한 kind.

failure-taxonomy.md 「kind와 `outcome`은 1:1이 아니다」 — 등재 kind 5종 중 나머지 4종은
eval이 「왜 못 읽었나」를 집계하는 분류이지 실행 실패가 아니다(`OVERLAY_VALIDATION`은 값을
읽은 **뒤의** 검증 결과다). 등재 code 3건도 전부 `INFRA` 아래에 있다.
"""


def _registered_failure(error: providers.ProviderError) -> Failure:
    """provider가 준 실패를 **등재 조합으로만** 계약에 싣는다.

    이 계약의 Producer는 readout이다 — provider가 등재되지 않은 값이나 층위가 다른 kind를
    error 채널로 올려도 그것을 그대로 `ReadoutRun.failure`에 실으면 미등재 값을 우리가
    발행하는 것이 된다(Merge 중단 기준 1). 그런 응답 자체가 파이프라인 오류이므로
    `INFRA`/`READOUT_PIPELINE_ERROR`로 닫는다 — 예외로 되돌리지는 않는다.
    """
    if error.kind == RUN_FAILURE_KIND and error.code in registry.FAILURE_CODES:
        return Failure(kind=error.kind, code=error.code)
    return Failure(kind=RUN_FAILURE_KIND, code="READOUT_PIPELINE_ERROR")


def _fail_run(run: ReadoutRun, error: providers.ProviderError) -> ReadoutRun:
    """완전 실패 — run만 남기고 결과 객체를 만들지 않는다(failure-taxonomy.md 「code」)."""
    run.outcome = "FAILED"
    run.failure = _registered_failure(error)
    run.ended_at = _now()
    return run


def _observation(value, status, source_kind, run_id, reason=None) -> Observation:
    return Observation(
        contract_version=OBSERVATION_VERSION,
        value=value,
        status=status,
        source={"kind": source_kind},
        # readout의 support_refs는 항상 빈 배열이다 — 근거 ref는 best_frame·frame_results가 갖는다.
        support_refs=[],
        produced_by=ProducedBy(
            module=MODULE, run_ref=ContractRef(kind="readout_run", ref=run_id),
        ),
        reason=reason,
    )


# ── read_plate ───────────────────────────────────────────────

def _consensus_of(texts):
    """프레임별 OCR 문자열을 모아 합의 문자열과 불일치 위치를 만든다.

    합의는 **문자열 다수결**이다 — 같은 문자열을 읽은 프레임이 `MIN_AGREEING_FRAMES` 이상이고
    과반이면 그 문자열이 합의다. 자리별 다수결을 쓰지 않는 이유는 테두리·볼트를 글자로 읽어
    한 자리가 더 붙은 프레임이 섞이면 자리가 밀려 엉뚱한 문자열을 조립하기 때문이다(Laroca
    2023, arXiv 2309.04331 — 문자열 다수결 90.1% vs 자리별 87.6%).

    다수결이 안 되면 예전 만장일치로 본다 — 한 자리에서 하나라도 다르면 `?`. 길이가 다르면
    자리를 맞출 수 없다 — 합의 문자열 없이 불일치로만 처리한다. 그래서 1~2장이 모두 같게 읽은
    경우는 지금도 합의다. 「3장 미만은 확정하지 않는다」는 공용 Mock Pack(`data/mock/readout/`의
    2장 OK 시나리오)과 case 테스트가 기대는 동작을 바꾸므로 따로 합의한 뒤 넣는다.
    """
    usable = [t for t in texts if t]
    if not usable:
        return "", [], False
    top, votes = Counter(usable).most_common(1)[0]
    if votes >= MIN_AGREEING_FRAMES and votes * 2 > len(usable):
        return top, [], False
    if len({len(t) for t in usable}) > 1:
        return "", [], True

    chars = []
    positions = []
    for i, column in enumerate(zip(*usable)):
        if len(set(column)) == 1:
            chars.append(column[0])
        else:
            chars.append("?")
            positions.append(i)
    return "".join(chars), positions, bool(positions)


def _best_index(frames, agreed=None):
    """대표 근거 프레임의 **자리**. 신뢰도 우선, 같으면 선명도, 그래도 같으면 먼저 온 것.

    객체가 아니라 index를 주는 이유 — 같은 프레임에서 뜬 영역이 둘이면 reading 객체만으로는
    어느 crop이 그것인지 고를 수 없다.

    합의 문자열(`agreed`)이 있으면 그 문자열을 읽은 프레임 중에서만 고른다 — 소수 프레임이
    옆 차량을 읽었을 때 그 crop이 대표 근거로 올라가지 않게 한다.
    """
    readable = [i for i, f in enumerate(frames) if f.text and (agreed is None or f.text == agreed)]
    if not readable:
        return None
    return max(
        readable,
        key=lambda i: (
            frames[i].confidence if frames[i].confidence is not None else -1.0,
            frames[i].quality.get("sharpness", -1.0),
        ),
    )


def _abstain_reason(association, best, disagreed):
    """보류 사유는 **단일 값**이다. 우선순위는 `association > frame consensus`.

    association이 애매하면 프레임 합의 이전 단계에서 걸린 것이므로 `TARGET_AMBIGUOUS`가
    authoritative다(failure-taxonomy.md 「사유가 겹칠 때 우선순위」). 그 아래에서는 해상도를
    신뢰도보다 앞에 둔다 — 낮은 신뢰도는 대개 낮은 해상도의 증상이고, 사용자에게 할 수 있는
    말이 다르다.

    `LOW_CONFIDENCE`·`NOT_PROVIDED` association은 보류를 강제하지 않는다. 그 둘로 최종 확정을
    보류할지는 `evidence`가 정한다(계약 §5 「target_association.status」).
    """
    if association.status in ("AMBIGUOUS", "FAILED"):
        return "TARGET_AMBIGUOUS"
    if disagreed:
        return "FRAME_DISAGREEMENT"
    if best is not None:
        # 대상 crop은 검출용으로 한글이 빠진 숫자 문자열도 보존한다. 다만 이것은
        # 사용자가 확대 이미지를 보고 완성해야 하는 부분 판독이므로 자동 확정하지 않는다.
        if best.text and not re.search(r"[가-힣]", best.text):
            return "OCR_LOW_CONFIDENCE"
        # 황색 2줄 번호판의 아랫줄(`바5215`)처럼 형식이 온전하지 않은 값은 번호판 일부다.
        # 관찰값은 보존하지만 자동 확정하지 않는다.
        if not FULL_PLATE.fullmatch(best.text):
            return "PARTIAL_PLATE_READ"
        height = best.quality.get("plate_px_height")
        if height is not None and height < MIN_PLATE_PX_HEIGHT:
            return "LOW_RESOLUTION"
        if best.confidence is not None and best.confidence < PLATE_ACCEPT_CONFIDENCE:
            return "OCR_LOW_CONFIDENCE"
    return None


def read_plate(request: ReadRequest, target_hint: Optional[TargetHint] = None,
               provider: Optional[providers.OcrProvider] = None) -> PlateReadResult:
    """번호판을 관찰한다. 확정하지 않는다.

    `target_hint`는 optional이다 — 없으면 provider가 자체 association을 시도하고, 무엇을 대상으로
    읽었는지는 어느 쪽이든 `target_association`에 남는다.

    반환은 `(ReadoutRun, PlateReadout | None)`. provider가 완전 실패하면 두 번째가 `None`이다.
    """
    _validate_input_ref(request.input_ref)
    provider = provider or providers.default_provider()
    run = _start_run("PLATE_READ", request)

    try:
        reading = provider.read_plate(request.input_ref, target_hint)
    except providers.ProviderError as error:
        return PlateReadResult(_fail_run(run, error), None)

    try:
        plate = _interpret_plate(reading, target_hint, request, run.run_id)
    except providers.ProviderError as broken:
        # 해석 중 우리가 **알아본** 계약 위반. detail이 이미 무엇이 어긋났는지 말한다.
        return PlateReadResult(_fail_run(run, broken), None)
    except Exception as unexpected:  # noqa: BLE001 — 아래 이유로 넓게 잡는다
        # provider 데이터를 해석하다 터진 것은 전부 여기로 온다. 예외로 되돌리면 실행이
        # 일어났는데 run이 없는 상태가 되어 worker가 발행 근거를 잃는다(모듈 docstring).
        return PlateReadResult(_fail_run(run, _provider_broke_contract(
            f"plate 응답 해석 중 예기치 못한 오류: {unexpected!r}")), None)

    run.ended_at = _now()
    return PlateReadResult(run, plate)


def _interpret_plate(reading, target_hint, request, run_id) -> PlateReadout:
    """provider가 준 plate 응답을 계약 값으로 옮긴다 — association 반영·consensus·abstain·조립.

    **provider 데이터에 손이 닿는 계산은 전부 여기 모여 있다.** 호출자가 이 함수 하나만
    감싸면 「provider를 부른 뒤에는 예외를 내보내지 않는다」가 성립한다 — `bbox_xywh`가
    비어 오는 것처럼 우리가 미리 못 본 값이 들어와도 실패 run으로 닫힌다
    (`_interpret_overlay`와 같은 구조다).
    """
    association = reading.association
    if association.target_hint_used and target_hint is None:
        raise _provider_broke_contract(
            "provider가 target_hint를 썼다고 보고했으나 hint가 없었다")

    # 번호판 번호에 공백은 없다 — `12가 3456`처럼 띄어 읽힌 값을 여기서 한 번 붙인다.
    frames = [replace(f, text=re.sub(r"\s+", "", f.text) if f.text else f.text)
              for f in reading.frames]
    crop_refs = _issue_crop_refs(frames)
    frame_results = [
        FrameResult(
            frame_ref=f.frame_ref,      # 파싱하지 않고 그대로 보존한다
            crop_ref=crop_ref,
            text=f.text,
            confidence=f.confidence,
        )
        for f, crop_ref in zip(frames, crop_refs)
    ]

    text, disagree_positions, disagreed = _consensus_of([f.text for f in frames])
    best_at = _best_index(frames, None if disagreed else text)
    best = frames[best_at] if best_at is not None else None
    reason = _abstain_reason(association, best, disagreed)
    abstained = reason is not None

    if text:
        value, status = text, "NEEDS_REVIEW" if abstained else "OK"
    elif disagreed:
        # 자리를 맞출 수 없어 합의 문자열이 없다. 그래도 불일치는 불일치다 — 여기서 보류를
        # 지우면 「모름」과 「프레임이 어긋나 보류」가 한 값으로 합쳐지고, abstained=false로
        # 내려간 것이 eval의 Wrong Accept 분모에 들어간다.
        value, status = None, "NEEDS_REVIEW"
    else:
        # 읽어낸 글자가 없다. 보류가 아니라 「알 수 없음」이다 — 보류할 관찰값 자체가 없다.
        value, status = None, "UNKNOWN"
        abstained, reason = False, None

    # 대상 차량 영역은 association이 소유한다. 대표 프레임의 번호판 박스에서 만들지 않는다 —
    # 그러면 「어느 차량을 읽었나」와 「번호판이 어디 있나」가 한 값이 되고, 계약 §4가
    # `plate_bbox_xywh`를 따로 둔 이유가 사라진다. 둘은 프레임이 다를 수도 있다.
    region = None
    if association.region is not None:
        frame_ref, bbox = association.region
        region = AssociatedRegion(frame_ref=frame_ref, bbox_xywh=list(bbox))

    return PlateReadout(
        readout_id=_new_id("readout"),
        run_ref=ContractRef(kind="readout_run", ref=run_id),
        case_id=request.case_id,
        candidate_id=request.candidate_id,
        input_ref=_copy_input_ref(request.input_ref),
        target_association=TargetAssociation(
            status=association.status,
            target_hint_used=association.target_hint_used,
            track_ref=association.track_ref,
            association_method=association.association_method,
            associated_region=region,
            evidence=[AssociationEvidence(kind=k, detail=d) for k, d in association.evidence],
        ),
        # abstain일 때 observation.reason을 중복 채우지 않는다 — abstain_reason이 authoritative다.
        observation=_observation(value, status, "readout.plate_ocr", run_id),
        consensus=Consensus(
            text=text,
            disagree_positions=disagree_positions,
            method="MULTI_FRAME" if len([f for f in frames if f.text]) > 1
            else "SINGLE_FRAME",
        ),
        abstained=abstained,
        abstain_reason=reason,
        # PARTIAL_PLATE_READ의 bbox는 2줄 번호판 중 텍스트 한 줄일 수 있다. 이를
        # 전체 번호판 bbox로 내보내 Case가 PLATE_IMAGE를 잘못 만들게 하지 않는다.
        best_frame=BestFrame(
            frame_ref=best.frame_ref,
            crop_ref=crop_refs[best_at],
            quality=dict(best.quality),
            # provider가 프레임마다 돌려주던 값을 여기서 버리고 있었다 (v1.3에서 실었다).
            # 새로 만드는 값이 아니라 대표 프레임의 번호판 영역을 그대로 싣는 것이다.
            plate_bbox_xywh=list(best.bbox_xywh),
        ) if best is not None and reason != "PARTIAL_PLATE_READ" else None,
        frame_results=frame_results,
        contract="PlateReadout",
        contract_version=PLATE_READOUT_VERSION,
    )


# ── read_overlay_time ────────────────────────────────────────

def _parse_overlay_text(raw, tz_offset):
    """overlay OCR 원문에서 시각을 뽑는다. **원문 전체가 시각일 것을 요구하지 않는다.**

    블랙박스는 시각 옆에 다른 값을 같은 줄에 찍는다. 실측(`20260810_175721_EVT_1`,
    conf 0.9724)에서 OCR이 돌려준 것은 이렇다 —

        '2026/08/10 17:57:36 13.20 ×:+0.020 Y:-0.043 2:-0.012'

    뒤쪽은 속도와 G센서 값이고 provider가 떼어 주지 않는다. 원문 전체를 `strptime`에
    넣으면 시각이 멀쩡히 찍혀 있는데도 `format_ok=false`로 떨어진다 — fixture는 깨끗한
    문자열이라 통과했지만 실제 영상에서는 전부 여기서 막힌다.

    그래서 **시각으로 보이는 부분을 먼저 찾고 그 부분만** 등재 형식으로 해석한다.
    원문은 `OverlaySample.raw_text`에 그대로 남으므로 무엇을 보고 뽑았는지 추적할 수 있다.

    한 줄에 시각이 둘 이상이면 **처음 것**을 쓴다. 어느 것이 프레임 시각인지 고를 근거가
    여기 없고, 임의로 고르면 그 판정이 이 함수에 숨는다.
    """
    if not raw:
        return None
    found = OVERLAY_TIME_IN_TEXT.search(raw)
    if found is None:
        return None
    stamp = found.group(0)
    for fmt in OVERLAY_TIME_FORMATS:
        try:
            parsed = datetime.strptime(stamp, fmt)
        except ValueError:
            continue
        return parsed.isoformat() + tz_offset
    return None


def _valid_tz_offset(raw) -> bool:
    """`tz_offset`이 **실제로 시각을 만들 수 있는 값**인지 판정한다.

    표기 검사만으로는 `+25:99`·`+09:60`처럼 자리 수는 맞고 시각은 아닌 값이 통과한다. 이 값은
    `_parse_overlay_text`에서 ISO 문자열 뒤에 그대로 이어 붙고 `_seconds_between`이
    `fromisoformat`으로 다시 읽으므로, 여기서 못 거르면 해석 단계에서 터진다 — 그때는 이미
    provider를 부른 뒤라 예외로 되돌릴 수 없는 자리다(모듈 docstring).

    표기 검사를 남겨 둔 이유 — `%z`는 `+0900`도 유효한 offset으로 받지만 계약이 정한 표기는
    `±HH:MM`·`Z` 둘뿐이다. **표기는 계약이 정하고, 유효성은 `strptime`이 판정한다.**
    """
    if not raw or not TZ_OFFSET.fullmatch(raw):
        return False
    try:
        datetime.strptime(raw, "%z")
    except ValueError:
        # 범위를 벗어난 offset — `%z`는 ±24시간 밖을 시각으로 인정하지 않는다.
        return False
    return True


def _seconds_between(earlier, later) -> float:
    return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()


def _validate_samples(samples):
    """읽어낸 sample들로 `monotonic_ok` · `duration_match_ok`를 판정한다.

    둘 다 sample이 2건 이상 있어야 볼 수 있다. 볼 수 없으면 `false`가 아니라 `null`이다 —
    「검증 안 함」과 「검증했는데 틀렸다」는 다르다(계약 §7).
    """
    ordered = sorted(samples, key=lambda s: s[0])  # (offset_sec, parsed_at)
    if len(ordered) < 2:
        return None, None

    monotonic_ok = all(
        _seconds_between(ordered[i][1], ordered[i + 1][1]) >= 0
        for i in range(len(ordered) - 1)
    )

    duration_match_ok = True
    for i in range(len(ordered) - 1):
        offset_delta = ordered[i + 1][0] - ordered[i][0]
        clock_delta = _seconds_between(ordered[i][1], ordered[i + 1][1])
        tolerance = OVERLAY_QUANTIZATION_SEC + abs(offset_delta) * OVERLAY_DRIFT_RATIO
        if abs(clock_delta - offset_delta) > tolerance:
            duration_match_ok = False
            break

    return monotonic_ok, duration_match_ok


def read_overlay_time(request: ReadRequest,
                      provider: Optional[providers.OcrProvider] = None) -> OverlayTimeReadResult:
    """화면에 찍힌 시각을 관찰하고 검증한다. 최종 발생 시각을 고르지 않는다.

    네 갈래를 서로 다른 값으로 남긴다 — 읽음(`OK`) / 없음(`NOT_APPLICABLE` + `not_present`) /
    있는지 못 봄(`UNKNOWN` + `presence_undetermined`) / 읽었으나 못 알아봄(`UNKNOWN` +
    `ocr_failed`). 뒤 셋은 실행 실패가 아니므로 `outcome`은 `SUCCEEDED`이고 결과 객체를 만든다
    (failure-taxonomy.md 「실패가 아닌 상태」).

    반환은 `(ReadoutRun, OverlayTimeReadout | None)`.
    """
    _validate_input_ref(request.input_ref)
    provider = provider or providers.default_provider()
    run = _start_run("OVERLAY_TIME_READ", request)

    try:
        reading = provider.read_overlay_time(request.input_ref)
    except providers.ProviderError as error:
        return OverlayTimeReadResult(_fail_run(run, error), None)

    if reading.presence not in providers.PRESENCES:
        return OverlayTimeReadResult(_fail_run(run, _provider_broke_contract(
            f"provider가 모르는 presence를 보고했다: {reading.presence!r}")), None)
    if reading.presence != providers.PRESENT and reading.samples:
        return OverlayTimeReadResult(_fail_run(run, _provider_broke_contract(
            f"presence={reading.presence}인데 sample이 있다 — 읽은 것이 있으면 PRESENT다")), None)

    if not _valid_tz_offset(reading.tz_offset):
        return OverlayTimeReadResult(_fail_run(run, _provider_broke_contract(
            f"provider가 시각을 만들 수 없는 tz_offset을 줬다: {reading.tz_offset!r}")), None)

    try:
        samples, value, status, reason_code, validation = _interpret_overlay(reading)
    except Exception as unexpected:  # noqa: BLE001 — 아래 이유로 넓게 잡는다
        # provider 데이터를 해석하다 터진 것은 전부 여기로 온다. 예외로 되돌리면 실행이
        # 일어났는데 run이 없는 상태가 되어 worker가 발행 근거를 잃는다(모듈 docstring).
        return OverlayTimeReadResult(_fail_run(run, _provider_broke_contract(
            f"sample 해석 중 예기치 못한 오류: {unexpected!r}")), None)

    reason = ObservationReason(code=reason_code, note=None) if reason_code else None
    overlay = OverlayTimeReadout(
        readout_id=_new_id("readout"),
        run_ref=ContractRef(kind="readout_run", ref=run.run_id),
        case_id=request.case_id,
        candidate_id=request.candidate_id,
        input_ref=_copy_input_ref(request.input_ref),
        observation=_observation(value, status, "readout.overlay_ocr", run.run_id, reason),
        validation=validation,
        samples=samples,
        contract="OverlayTimeReadout",
        contract_version=OVERLAY_TIME_READOUT_VERSION,
    )
    # validation 실패는 run 실패가 아니다 — outcome을 내리지 않는다(failure-taxonomy.md).
    run.ended_at = _now()
    return OverlayTimeReadResult(run, overlay)


def _interpret_overlay(reading):
    """provider가 준 sample을 계약 값으로 옮긴다 — 4갈래와 validation 3종.

    **provider 데이터에 손이 닿는 계산은 전부 여기 모여 있다.** 호출자가 이 함수 하나만
    감싸면 「provider를 부른 뒤에는 예외를 내보내지 않는다」가 성립한다 — 형식이 어긋난
    `tz_offset`처럼 우리가 미리 못 본 값이 들어와도 실패 run으로 닫힌다.

    반환은 `(samples, value, status, reason_code, OverlayValidation)`.
    """
    samples = [
        OverlaySample(
            frame_ref=s.frame_ref,      # 파싱하지 않고 그대로 보존한다
            offset_sec=s.offset_sec,
            raw_text=s.raw_text,
            parsed_at=_parse_overlay_text(s.raw_text, reading.tz_offset),
        )
        for s in reading.samples
    ]
    parsed = [(s.offset_sec, s.parsed_at) for s in samples if s.parsed_at]

    if reading.presence == providers.NOT_PRESENT:
        # 화면에 시각이 안 찍힌 영상 — 판독 실패가 아니라 대상이 없다는 정상 관찰 결과다.
        value, status = None, "NOT_APPLICABLE"
        reason_code = "readout.overlay.not_present"
        format_ok = monotonic_ok = duration_match_ok = None
    elif reading.presence == providers.UNDETERMINED or not samples:
        # 있는지 없는지 자체를 못 봤다. 「없음」과 합치지 않는다 — 없다고 하면 사용자가 화면을
        # 다시 보지 않는다(core-user-flow.md §5).
        value, status = None, "UNKNOWN"
        reason_code = "readout.overlay.presence_undetermined"
        format_ok = monotonic_ok = duration_match_ok = None
        samples = []
    elif len(parsed) < len(samples):
        # 보였고 읽기도 했는데 시각 형식으로 안 나왔다. 일부만 읽힌 것도 여기로 접는다 —
        # 섞인 상태를 `OK`로 내보내면 `format_ok=false`인 값이 확정처럼 소비된다.
        value, status = None, "UNKNOWN"
        reason_code = "readout.overlay.ocr_failed"
        format_ok, monotonic_ok, duration_match_ok = False, None, None
    else:
        value = min(parsed)[1]  # 가장 이른 프레임에서 읽힌 시각
        status, reason_code = "OK", None
        format_ok = True
        monotonic_ok, duration_match_ok = _validate_samples(parsed)

    return samples, value, status, reason_code, OverlayValidation(
        format_ok=format_ok,
        monotonic_ok=monotonic_ok,
        duration_match_ok=duration_match_ok,
        sample_count=len(samples),
    )
