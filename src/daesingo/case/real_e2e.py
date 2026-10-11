"""`scenario_happy_001` 대표 시나리오용 real E2E 파이프라인 — recording → search →
readout → evidence까지 전부 실제 공개 함수를 호출한다(W5/W6, 2026-09-22 월 20:00
회의 데드라인 대응).

기준은 "대표 시나리오 1개가 전체 흐름을 실제로 통과하는가"이지 모든 단계가 PASS
등급을 받는가가 아니다(요청 문서 "이번엔 안 해도 되는 것" — 모든 edge case·완성된
Worker 배선은 이번 범위 밖).

## 알려진 단순화 (정직하게 남김 — W7에서 메운다)

- **`time_source_candidates`**: recording의 `RecordingFixture` pydantic 모델에 이
  필드 자체가 없다(1차 구현 범위 밖) — 공개 함수로 노출된 적이 없으므로 recording의
  raw fixture JSON에서 그대로 읽는다. 이 한 곳만 mock이고 나머지는 전부 real 함수
  호출이다.
- **`situation_response`**: 2026-09-28부터 `CaseAggregate.record_situation_response()`로
  기록된 사용자 응답을 `assemble_evidence_bundle()`에 그대로 전달한다(#171 B-2 · 통합 항목
  I1). 응답 전에는 `None`(= `NOT_ASKED`)이고, ADR-EVIDENCE-005 D2-c에 따라 Package가 나가지
  않는다. web에서 응답을 보내는 경로(#106 command)는 아직 없다.
- **`observation_facts`**: case에 이 값을 만드는 로직이 아직
  없어 `None`으로 둔다. 그 결과 `FINAL_PACKAGE` 판정이 PASS/WARN에
  못 미쳐 `build_report_package()`가 `PackageNotReady`를 던질 수 있다 — 이건 실패가
  아니라 "정보가 부족해 아직 패키지를 못 만든다"는 실제 도메인 상태이고, `CaseView`의
  partial 표현이 원래 이런 상태를 위해 있다(`module-architecture.md` §5-12).
- **`gps_observation`**: recording이 GPS 관찰을 내놓는 공개 함수를 아직 노출하지 않아
  `None`으로 둔다. case의 자연어 위치 단서(`hints.location`)는 real 경로에 전달하지만,
  좌표(`location.coord`)는 GPS producer가 연결되기 전까지 비어 있을 수 있다.
- **시나리오 고정**: `scenario_happy_001` 하나로 고정돼 있다. 다른 시나리오로 넓히려면
  recording fixture 선택과 asset_facts 매핑을 다시 설계해야 한다(W7).

## Fine 결과 소비 (이슈 #137)

Fine은 `OBSERVED` 말고도 정상적인 결과를 낸다. `verification=NOT_OBSERVED`는 "영상은 봤고
실행도 성공했는데 이 후보를 지지하는 근거가 없다"는 뜻이고(`contract-visual-evidence.md`
§4-1), `EvidenceRecord`로 승격시키면 안 되는 유효한 negative 결과다. 그래서 이 파이프라인은
Fine 결과를 받자마자 `evidence.classify_visual_evidence()`로 분류하고, 조립 대상이 아니면
IncidentClip·readout·TimeResolution·evidence를 **시작하지 않고** 정상 종료한다 —
`EvidenceBundle`의 조립 산출물이 전부 `None`인 것이 그 상태다. `build_evidence_for_real_video_candidate()`도
같은 분류를 거친다(PR #131→#142 후속 정합화, 2026-09-22).

`UNCERTAIN`은 사용자가 「잘 모르겠어요」(`USER_UNSURE`)로 답하기 전까지
`AWAIT_SITUATION_RESPONSE`다(#165). 관찰 단계는 그대로 진행하고, `assemble_evidence_bundle()`이
응답까지 넣어 다시 분류해 응답 전에는 조립하지 않는다. 응답이 오면 조립만 다시 한다.
응답 전에도 상황 독립 값(번호판 · 시각 · 위치)은 evidence `resolve_independent_facts()`로 계산해
`EvidenceBundle.independent_facts`에 둔다 — CaseView `evidence` 부분 투영(`record_id=null`)의 원천이다(#239).

`NOT_OBSERVED`를 `UNCERTAIN` fallback으로 합치지 않는다. `UNCERTAIN + USER_UNSURE`는
사용자가 "잘 모르겠지만 진행"을 택한 generic 신고 경로이고, `NOT_OBSERVED`는 Fine이 후보를
기각한 것이라 둘을 합치면 관찰되지 않은 위반으로 신고문을 만들게 된다.

다음 후보를 자동으로 Fine하거나 가장 높은 후보를 자동 채택하는 정책은 여기 없다 —
`core-user-flow.md`가 정본화된 뒤 Product/Case/Evidence/Web이 함께 정할 후속 변경이다.

## 의존성 — 2026-09-21 develop 병합 완료(PR #128 search·#129 recording·#130 readout·#113 PaddleOCR)

`search.verify_visual_with_stream_context`/`AnalysisSourceStream`/`VideoStreamSelectionError`,
`recording.resolve_span(..., media_stream_ref=...)`/`register_local_source()`/
`create_relative_timeline()`/`AnalysisProfile`/`LocalAnalysisMaterializer` 전부
develop에 있다. 3개 gap 전부 종결(`doc/real-e2e-protocol.md`/`doc/real e2e 가능성
체크.md` 참고, 둘 다 git에 커밋되지 않는 로컬 전용 문서 — 실행 기록은
`docs/modules/case/experiments/real-e2e-20260922-monday-baseline.md`):

- **search에 실제 service 미주입 — 종결.** `RecordingAnalysisSourceResolver`(gateway로
  `rec_service`를 그대로 씀 — `open_analysis_source()` 시그니처가 구조적으로 일치)와
  `build_gemini_search_service(api_key, resolver)`로 `search_candidates()`/
  `verify_visual_with_stream_context()`에 `service=`를 실제로 넘긴다. API 키는
  `.env`의 `GEMINI_API_KEY`(커밋 안 됨, `daesingo.common.env.load_env_file()`로 읽음).
- **readout `FixtureOcrProvider` — 종결.** `PaddleOcrProvider(RecordingFrameSource(rec_service))`로
  **IncidentClip 구간 안의 프레임**을 읽는다(`_build_ocr_provider()`, 2026-09-28 — PR #146 멘토
  리뷰 r4084810910 후속). readout의 `RecordingFrameSource`(#138)가 recording 공개 경로
  (`get_incident_clip()` → `resolve_frame()` → `read_frame()`)로 프레임과 recording이 발급한
  `frame_ref`를 넘긴다. 예전엔 `LocalVideoFrameSource(원본 경로)`로 원본 파일 전체의
  30/50/70% 지점을 읽어 위반 구간 밖의 프레임을 볼 수 있었다. 샘플링 간격·장수는 readout이
  정한다(계약 §13 미결).
- **`time_source_candidates = []` — 종결.** `rec_service.observe_time_sources()`
  결과를 그대로 전달한다.

## `build_real_video_evidence_bundle()` — 월요일 real 영상 경로, 알려진 단순화

- **`profile_ref`**: 정철원 확인(2026-09-21, 이슈 #95 D2와는 별개 — D2는 이미 책임
  경계가 종결돼 월요일 실행이 기다릴 필요 없음) — 480p H.264, preset=veryfast,
  crf=23, audio off. 이 설정은 `profile_ref` 문자열에 인코딩되지 않고 실행 조립 시
  `LocalAnalysisMaterializer`에 명시적으로 등록한다. **최종 canonical profile
  이름·값 공간은 미확정** — `_MONDAY_ANALYSIS_PROFILE`은 이번 실행 안에서의
  동일성/재사용 판단용 opaque 설정일 뿐 계약 기본값이 아니다.
- **`AnalysisScope`의 `budget`/`target_event_types`**: case Producer 소유(recording
  소유 아님). 공용 Mock Pack의 happy 기준(`target_event_types=["SOLID_LINE_LANE_CHANGE"]`,
  `max_cost_krw:1000`)을 월요일 GT 없는 배관 E2E에 재사용한다(정철원 확인,
  2026-09-21) — `SOLID_LINE_LANE_CHANGE`는 실제 영상의 정답을 단정하는 값이 아니라
  search에 요청하는 탐지 대상이다. `max_latency_sec`는 2026-09-28부터 A-1 잠정값
  「Coarse 클립당 150초」(`docs/modules/case/decisions/timeout-fallback.md`, #72)를 쓴다 —
  이 경로는 영상 전체를 한 번에 올려 사실상 클립 1개이고, 인라인 상한을 넘는 영상은
  search가 `MediaTooLargeError`로 막는다. 클립 분할 발주는 #168 후속 결정 뒤 구현한다.
- **candidate 선택은 `candidates[0]`으로 고정한다.** GT 없는 배관 확인이 목적이라
  "어느 candidate가 맞는지"는 이번 범위 밖이다 — `happy_001`이 후보 1개라 우연히
  안전했던 것과 같은 자리다. 후보가 여럿이면 이 단순화가 그대로 드러난다.
- **readout provider는 여전히 `FixtureOcrProvider`다.** 실제 영상엔 맞지 않는
  provider이지만, 이건 readout Owner가 확인해야 할 별도 gap이라 이 파일이 대신
  풀지 않는다.
- **`RecordingService.close()`는 이 함수가 부르지 않는다.** search가
  `open_analysis_source()`로 바이트를 다 읽기 전에 닫으면 실행 중인 AnalysisSource가
  해제된다(정철원 확인, 2026-09-21) — 반환값에 `rec_service`를 포함해 호출자가 언제
  닫을지 스스로 결정하게 한다.
- **2026-09-22 실행 현황(`docs/modules/case/experiments/real-e2e-20260922-monday-baseline.md`
  참고, 상세 기록은 git 커밋 안 되는 `doc/`가 아니라 이 경로에 있다):** 대표 영상
  (`20260620_141956_EVT_1.avi`)으로 실제 실행 — `register_local_source()`~
  Coarse 실제 Elice/Gemini 호출~candidate 생성까지 성공, **Fine 이후는 search
  내부 정합성 검증 실패로 막힘**(이슈 #132, case 배선 문제 아님). Coarse/Fine만
  stub으로 바꾼 무료 dry-run으로는 IncidentClip~EvidenceRecord~RequirementReport까지
  전부 실제 데이터(실제 PaddleOCR·실제 time source 포함)로 끝까지 통과 확인함 —
  그 과정에서 실제 버그 2건(`incident_materializer` 누락, 로컬 analysis_source/
  incident_clip의 AssetFacts 미등록) 발견·수정.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from daesingo import search as search_module
from daesingo.case.domain import CaseAggregate
from daesingo.case.scope import build_analysis_scope
from daesingo.common.env import load_env_file
from daesingo.evidence import (
    ASSEMBLE,
    AWAIT_SITUATION_RESPONSE,
    NOT_ASSEMBLED,
    VisualEvidenceDisposition,
    assemble_evidence,
    build_report_package,
    calculate_evidence_needs,
    classify_visual_evidence,
    evaluate_requirements,
    resolve_independent_facts,
    resolve_time,
)
from daesingo.evidence.errors import PackageNotReady
from daesingo.readout import api as readout_api
from daesingo.readout import paddle_provider
from daesingo.readout import providers as readout_providers
from daesingo.readout.contracts import InputRef
from daesingo.recording import (
    AnalysisProfile,
    AssetSpan,
    IncidentClipEncoding,
    LocalAnalysisMaterializer,
    LocalIncidentMaterializer,
    RecordingService,
    SpanResolution,
    load_recording_fixture,
)
from daesingo.search.sources import RecordingAnalysisSourceResolver, SourceMeta

SCENARIO_ID = "scenario_happy_001"

# 공용 Mock Pack happy 기준(정철원 확인, 2026-09-21) — 계약 기본값으로 확정된 게
# 아니라 월요일 GT 없는 배관 E2E용 재사용 값이다.
_MONDAY_TARGET_EVENT_TYPES = ["SOLID_LINE_LANE_CHANGE"]
# A-1 잠정값(timeout-fallback.md, #72) — Coarse 클립당 150초. runtime 머신 재측정 후 확정.
_COARSE_CLIP_TIMEOUT_SEC = 150
_MONDAY_BUDGET = {"max_cost_krw": 1000, "max_latency_sec": _COARSE_CLIP_TIMEOUT_SEC}


class StreamSelectionError(Exception):
    """`SpanResolution.spans[]`에서 쓸 `AssetSpan`을 정확히 하나로 좁힐 수 없을 때.

    여러 VIDEO stream(front/rear 등)이 같은 시간대를 가리킬 수 있다는 게
    `contract-recording-timeline-asset-span.md` §9 불변식 7이 명시적으로 허용하는
    상황이다 — 그 상태에서 `spans[0]`을 조용히 쓰면 어떤 카메라가 선택됐는지가
    사실상 우연이 된다. 그래서 애매하면 조용히 넘어가지 않고 여기서 표면화한다.
    """


def _select_asset_span(
    resolution: SpanResolution, media_stream_ref: str | None
) -> AssetSpan:
    """`media_stream_ref`와 일치하는 span을 명시적으로 고른다.

    `media_stream_ref`가 없으면 span이 정확히 하나일 때만 그대로 쓴다(지금까지의
    단일 스트림 경로와 동일) — span이 여러 개면 어떤 stream인지 명시해야 한다.
    """
    candidates = resolution.spans
    if media_stream_ref is not None:
        candidates = [span for span in candidates if span.media_stream_ref == media_stream_ref]
    if len(candidates) != 1:
        raise StreamSelectionError(
            f"media_stream_ref={media_stream_ref!r}로 span을 하나로 좁힐 수 없습니다 "
            f"(일치하는 span {len(candidates)}개, 전체 {len(resolution.spans)}개). "
            "여러 stream이 같은 시간대를 가리키면 media_stream_ref를 명시해야 합니다."
        )
    return candidates[0]


def _unique_video_media_stream_ref(media_streams: Any) -> str:
    """등록된 `MediaStream` 중 `media_type == "VIDEO"`가 정확히 하나인지 검증하고 그
    ref를 반환한다.

    정철원(recording) 확인(2026-09-21) — 이건 "여러 VIDEO 후보 중 하나를 임의로
    고르는 것"이 아니라 **유일성 검증**이다. 월요일 대표 파일(`20260620_141956_EVT_1.avi`)은
    ffprobe 결과 VIDEO 1개/AUDIO 1개뿐이라(subtitle/data는 recording이 등록에서
    제외) 이 검증이 항상 통과해야 정상이다. VIDEO가 0개거나 여러 개면 recording이
    임의로 고르지 않듯 case도 임의로 고르지 않고 여기서 실패시킨다 — 일반적인 복수
    카메라 선택 정책은 W7 후속이다.
    """
    video_refs = [s.media_stream_ref for s in media_streams if s.media_type == "VIDEO"]
    if len(video_refs) != 1:
        raise StreamSelectionError(
            f"media_streams에서 media_type=VIDEO가 정확히 하나가 아닙니다"
            f"(VIDEO {len(video_refs)}개). 복수 카메라 선택 정책은 W7 후속이라 case가"
            " 여기서 임의로 고르지 않는다."
        )
    return video_refs[0]


def _match_analysis_source_streams(
    media_stream_refs: Any, media_streams: Any
) -> tuple[Any, ...]:
    """`AnalysisSource.media_stream_refs[]`의 각 ref를 등록된 `media_streams`(fixture의
    `RecordingFixture.media_streams` 또는 `register_local_source()`가 돌려준
    `RegisteredSource.media_streams`)에서 찾아 `search.AnalysisSourceStream`으로
    변환한다.

    누락(매칭 0개)되거나 중복 매칭(2개 이상)되면 fixture 값으로 보정하지 않고 여기서
    실패시킨다(정철원 확인, 2026-09-21) — search가 stream을 임의로 고르지 않는 것과
    같은 원칙이다.
    """
    streams: list[Any] = []
    for ref in media_stream_refs:
        matches = [s for s in media_streams if s.media_stream_ref == ref]
        if len(matches) != 1:
            raise StreamSelectionError(
                f"AnalysisSource.media_stream_refs의 {ref!r}가 등록된 media_streams에서"
                f" 정확히 하나로 매칭되지 않습니다(매칭 {len(matches)}개)."
            )
        streams.append(
            search_module.AnalysisSourceStream(
                media_stream_ref=ref, media_type=matches[0].media_type
            )
        )
    return tuple(streams)


def _resolve_via_search_stream_context(
    *,
    analysis_source: Any,
    media_streams: Any,
    candidate: search_module.CandidateEvent,
    target_hint: Any,
    service: Any = None,
) -> tuple[Any, str]:
    """`AnalysisSource.media_stream_refs`를 등록된 `media_streams`와 매칭해 search의
    실행 문맥 API를 부르고, `(VisualVerificationResult, 선택된 media_stream_ref)`를
    돌려준다. fixture 경로(`build_happy_001_evidence_bundle`)와 실제 영상 경로
    (`build_real_video_evidence_bundle`)가 공유한다.

    `service`가 `None`이면 search 자체 fixture로 빠진다(`verify_visual_with_stream_context`
    기본값 그대로) — 실제 영상 경로는 real `SearchService`를 넘겨서 Fine이 Elice ML
    API를 실제로 부르게 한다.
    """
    analysis_source_streams = _match_analysis_source_streams(
        analysis_source.media_stream_refs, media_streams
    )
    execution = search_module.verify_visual_with_stream_context(
        input_ref=search_module.ContractRef(
            kind="analysis_source", ref=analysis_source.analysis_source_ref
        ),
        candidate=candidate,
        analysis_source_streams=analysis_source_streams,
        target_hint=target_hint,
        service=service,
    )
    return execution.result, execution.selected_video_stream.media_stream_ref


@dataclass
class EvidenceBundle:
    """Fine 결과를 소비한 결과. `NOT_OBSERVED`면 조립 산출물 쪽이 전부 `None`이다.

    `visual_evidence`/`fine_run`/`disposition`은 어느 결말에서도 채워진다 — Fine이
    후보를 기각했다는 것도 평가·진단에 쓰이는 관찰 결과라서(`adr-visual-evidence.md`)
    조립을 하지 않는다고 지워버리면 안 된다. `fine_run`에 `usage_refs`/`usage_summary`가
    들어 있어 비용 기록도 같이 남는다.
    """

    evidence_record: dict[str, Any] | None
    evidence_needs: dict[str, Any] | None
    requirement_report_evidence: dict[str, Any] | None
    requirement_report_package: dict[str, Any] | None
    report_package: dict[str, Any] | None
    package_error: str | None
    visual_evidence: dict[str, Any]
    fine_run: dict[str, Any]
    disposition: VisualEvidenceDisposition
    # 조립에 쓴 `PlateReadout`(판독 결과가 없거나 조립 전이면 `None`). CaseView
    # `evidence.plate_preview_ref`(#47)가 `best_frame.frame_ref`를 여기서 찾는다.
    plate_readout: dict[str, Any] | None = None
    # 번호판 판독 실행 결과 `ReadoutRun.outcome`(SUCCEEDED·PARTIAL·FAILED). 판독을 시작하지
    # 않았으면(NOT_OBSERVED) None. `FAILED`면 PlateReadout이 없어 evidence는 번호판 없이
    # 조립되므로, 실행 실패를 「읽지 못함」과 가르려면 이 값이 필요하다(#172 [D]).
    plate_read_outcome: str | None = None
    # 관찰 단계의 `OverlayTimeReadout`(판독하지 않았으면 `None`). 시각을 얻지 못한 갈래의 notice
    # (`readout.overlay_*`)가 `observation.reason.code`를 여기서 읽는다 — evidence 조립 전에도 필요하다.
    overlay_readout: dict[str, Any] | None = None
    # 상황 응답 대기(`AWAIT_SITUATION_RESPONSE`)에서만 채운다 — evidence `resolve_independent_facts()`가
    # 만든 상황 독립 값(`occurred_at` · `vehicle_number` · `location`, EvidenceRecord 같은 필드 모양). CaseView
    # `evidence`의 부분 투영(`record_id=null`, #239) 원천이다. EvidenceRecord가 아니다.
    independent_facts: dict[str, Any] | None = None

    @property
    def assembled(self) -> bool:
        return self.evidence_record is not None


@dataclass
class ObservationBundle:
    """선택된 candidate 하나에 대한 관찰 단계(Fine·IncidentClip·OCR·시간 source·AssetFacts)
    결과. 사용자 정정과 무관하게 정해지는 값만 담는다.

    이슈 #73 WARN ① — 부분 재실행 정책 표에서 `EVENT_TIME_MANUAL`·`REPORT_TYPE_CHANGE` 등은
    "요건 검사만 다시, 절대 안 건드리는 것: 전부"다. 정정이 들어오면 이 묶음은 그대로 두고
    `assemble_evidence_bundle()`(시각·evidence·요건·Package)만 다시 부른다. `NOT_OBSERVED`면
    조립할 것이 없어 `incident_clip` 이하가 전부 `None`/빈 값이다.
    """

    candidate: search_module.CandidateEvent
    visual_evidence: dict[str, Any]
    fine_run: dict[str, Any]
    disposition: VisualEvidenceDisposition
    incident_clip: dict[str, Any] | None = None
    plate_readout: dict[str, Any] | None = None
    overlay_readout: dict[str, Any] | None = None
    time_source_candidates: list[dict[str, Any]] = field(default_factory=list)
    asset_facts: list[dict[str, Any]] = field(default_factory=list)
    # 번호판 판독 `ReadoutRun.outcome`(#172 [D]). 판독을 시작하지 않았으면 None.
    plate_read_outcome: str | None = None


def assemble_evidence_bundle(
    observations: ObservationBundle,
    *,
    case_id: str,
    selection_rev: int = 1,
    correction_records: list[dict[str, Any]] | None = None,
    location_hint: str | None = None,
    situation_response: dict[str, Any] | None = None,
) -> EvidenceBundle:
    """관찰 결과로 TimeResolution → EvidenceRecord → Needs → RequirementReport 2종 →
    ReportPackage를 조립한다. 다른 모듈 호출 없이 evidence 순수 함수만 부르므로, 정정이
    들어올 때마다 다시 불러도 Search·Fine·readout은 다시 돌지 않는다(이슈 #73).

    `correction_records`는 case의 사용자 정정을, `situation_response`는 사용자의 신고 상황
    응답을 evidence 계산에 그대로 전달한다(`None` = 응답 전 `NOT_ASKED`, 통합 항목 I1).

    조립 여부는 사용자 응답까지 넣어 여기서 다시 분류한다(#165). Fine `UNCERTAIN`은
    `USER_UNSURE` 응답이 오기 전까지 `AWAIT_SITUATION_RESPONSE`라 조립하지 않고 관찰 결과만
    돌려준다 — 응답이 오면 같은 관찰 결과로 이 함수만 다시 부르면 된다. 무응답을
    `USER_UNSURE`로 채우지 않는다(#171 B-2).
    """
    obs = observations
    disposition = classify_visual_evidence(obs.visual_evidence, situation_response)
    candidate_event = obs.candidate.model_dump(mode="json")
    if disposition.decision == AWAIT_SITUATION_RESPONSE:
        # 응답 전에는 EvidenceRecord를 만들지 않고(#171 B-2), 이미 확보한 상황 독립 값만 evidence 규칙
        # 그대로 계산해 둔다(#239). 번호판 · 시각 · 위치 규칙은 evidence 한 곳에 있다 — 여기서 다시 만들지 않는다.
        time_resolution = resolve_time(
            time_source_candidates=obs.time_source_candidates,
            overlay_time_readout=obs.overlay_readout,
            candidate_event=candidate_event,
            correction_records=correction_records or [],
            case_id=case_id,
            selection_rev=selection_rev,
            resolution_id=f"tr_{case_id}_001",
        )
        return EvidenceBundle(
            evidence_record=None,
            evidence_needs=None,
            requirement_report_evidence=None,
            requirement_report_package=None,
            report_package=None,
            package_error=None,
            visual_evidence=obs.visual_evidence,
            fine_run=obs.fine_run,
            disposition=disposition,
            plate_read_outcome=obs.plate_read_outcome,
            plate_readout=obs.plate_readout,
            overlay_readout=obs.overlay_readout,
            independent_facts=resolve_independent_facts(
                case_id=case_id,
                selection_rev=selection_rev,
                time_resolution=time_resolution,
                plate_readout=obs.plate_readout,
                location_hint=location_hint,
                # GPS 단순화 (모듈 docstring 참고).
                gps_observation=None,
                correction_records=correction_records or [],
            ),
        )
    if disposition.decision != ASSEMBLE:
        return EvidenceBundle(
            evidence_record=None,
            evidence_needs=None,
            requirement_report_evidence=None,
            requirement_report_package=None,
            report_package=None,
            package_error=None,
            visual_evidence=obs.visual_evidence,
            fine_run=obs.fine_run,
            disposition=disposition,
            plate_read_outcome=obs.plate_read_outcome,
            overlay_readout=obs.overlay_readout,
        )

    time_resolution = resolve_time(
        time_source_candidates=obs.time_source_candidates,
        overlay_time_readout=obs.overlay_readout,
        candidate_event=candidate_event,
        correction_records=correction_records or [],
        case_id=case_id,
        selection_rev=selection_rev,
        resolution_id=f"tr_{case_id}_001",
    )

    evidence_record = assemble_evidence(
        case_id=case_id,
        selection_rev=selection_rev,
        candidate_event=candidate_event,
        visual_evidence=obs.visual_evidence,
        time_resolution=time_resolution,
        plate_readout=obs.plate_readout,
        incident_clip=obs.incident_clip,
        record_id=f"er_{case_id}_001",
        location_hint=location_hint,
        situation_response=situation_response,
        # GPS 단순화 (모듈 docstring 참고).
        gps_observation=None,
        correction_records=correction_records or [],
    )

    evidence_needs = calculate_evidence_needs(
        evidence_record,
        obs.plate_readout,
        emit_empty=True,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    requirement_report_evidence = evaluate_requirements(
        evidence_record,
        scope="EVIDENCE",
        report_id=f"rr_{case_id}_evidence",
        evaluated_at=now,
        time_resolution=time_resolution,
    )
    requirement_report_package = evaluate_requirements(
        evidence_record,
        scope="FINAL_PACKAGE",
        report_id=f"rr_{case_id}_package",
        evaluated_at=now,
        time_resolution=time_resolution,
        asset_facts=obs.asset_facts,
        # 알려진 단순화 2와 같은 이유로 None (모듈 docstring 참고).
        observation_facts=None,
    )

    report_package: dict[str, Any] | None = None
    package_error: str | None = None
    try:
        report_package = build_report_package(
            evidence_record,
            requirement_report_package,
            package_id=f"pkg_{case_id}_001",
            created_at=now,
            asset_facts=obs.asset_facts,
        )
    except PackageNotReady as exc:
        package_error = str(exc)

    return EvidenceBundle(
        evidence_record=evidence_record,
        evidence_needs=evidence_needs,
        requirement_report_evidence=requirement_report_evidence,
        requirement_report_package=requirement_report_package,
        report_package=report_package,
        package_error=package_error,
        visual_evidence=obs.visual_evidence,
        fine_run=obs.fine_run,
        disposition=disposition,
        plate_read_outcome=obs.plate_read_outcome,
        plate_readout=obs.plate_readout,
        overlay_readout=obs.overlay_readout,
    )


def build_happy_001_evidence_bundle(
    *,
    case_id: str,
    candidate: search_module.CandidateEvent,
    scope: search_module.AnalysisScope,
    mock_root: Path,
    selection_rev: int = 1,
    correction_records: list[dict[str, Any]] | None = None,
    location_hint: str | None = None,
) -> EvidenceBundle:
    """recording → `search.verify_visual_with_stream_context` → readout → evidence까지
    실제 함수로 이어서 실행한다. 모듈 docstring의 "알려진 단순화" 두 곳만 raw
    fixture/`None`이고 나머지는 전부 각 모듈의 공개 함수 호출 결과다.

    `observe_happy_001_candidate()` + `assemble_evidence_bundle()`을 이어 부른다. 정정 후
    다시 계산할 때는 관찰 결과를 재사용하고 조립만 다시 부른다(이슈 #73, `RealAdapter`).
    """
    observations = observe_happy_001_candidate(
        case_id=case_id, candidate=candidate, scope=scope, mock_root=mock_root
    )
    return assemble_evidence_bundle(
        observations,
        case_id=case_id,
        selection_rev=selection_rev,
        correction_records=correction_records,
        location_hint=location_hint,
    )


def observe_happy_001_candidate(
    *,
    case_id: str,
    candidate: search_module.CandidateEvent,
    scope: search_module.AnalysisScope,
    mock_root: Path,
) -> ObservationBundle:
    """`build_happy_001_evidence_bundle()`의 관찰 단계 — recording → Fine → IncidentClip →
    readout(fixture OCR) → 시간 source·AssetFacts까지. 정정과 무관한 값만 만든다."""
    fixture = load_recording_fixture(SCENARIO_ID)
    rec_service = RecordingService.from_fixture(fixture, case_id=case_id)

    # candidate.span을 recording.resolve_span() 입력으로 변환한다 — ms→sec는
    # recording 경계에서 명시적으로 한다(`contract-analysis-scope.md` §12 B08).
    timeline_ref = {
        "timeline_id": candidate.span.timeline_id,
        "revision": candidate.span.timeline_revision,
    }
    requested_range = {
        "start_sec": candidate.span.start_ms / 1000,
        "end_sec": candidate.span.end_ms / 1000,
    }
    resolution = rec_service.resolve_span(timeline_ref, requested_range)

    # AnalysisSource는 source_asset_ref+timeline_range+profile로 찾아지고(recording의
    # find_analysis_sources가 `media_stream_ref in media_stream_refs[]`로 매칭),
    # 어떤 span을 넘기든 같은 그룹의 AnalysisSource가 나온다 — 실제로 어떤 VIDEO
    # stream을 분석에 쓸지는 이 다음 search가 고른다.
    analysis_source = rec_service.prepare_analysis_source(
        resolution.spans[0].model_dump(mode="json"),
        fixture.analysis_sources[0].profile_ref,
    )

    # search와 합의한 stream 선택 경계(2026-09-21, 정철원·서어진) — search가 실제로
    # 분석에 쓴 VIDEO stream ref 하나를 `CandidateEvent`/`VisualVerificationResult`의
    # canonical 계약은 바꾸지 않고 별도 실행 문맥으로 돌려준다. media_type은 월요일
    # 범위에서 `fixture.media_streams`로 읽는다(실제 영상에서는
    # `RegisteredSource.media_streams` — 모듈 docstring 참고).
    visual_result, media_stream_ref = _resolve_via_search_stream_context(
        analysis_source=analysis_source,
        media_streams=fixture.media_streams,
        candidate=candidate,
        target_hint=scope.hint,
    )
    visual_evidence = visual_result.visual_evidence.model_dump(mode="json")
    fine_run = visual_result.analysis_run.model_dump(mode="json")

    # Fine 결과를 downstream(두 번째 resolve_span·IncidentClip 포함)으로 밀어넣기 전에
    # 먼저 분류한다(이슈 #137). `NOT_OBSERVED`는 실행 실패가 아니라 "이 후보는 아니다"라는
    # 유효한 관찰 결과이므로, IncidentClip·readout·TimeResolution·evidence 조립을
    # 시작하지 않고 여기서 정상 종료한다. 다음 후보를 자동으로 고르는 정책은 이번 범위가
    # 아니다 — `core-user-flow.md`가 정본화된 뒤 별도로 결정한다.
    disposition = classify_visual_evidence(visual_evidence)
    if disposition.decision == NOT_ASSEMBLED:
        return ObservationBundle(
            candidate=candidate,
            visual_evidence=visual_evidence,
            fine_run=fine_run,
            disposition=disposition,
        )

    # 두 번째 resolve_span() (정철원 정정, 2026-09-21) — recording이 이제
    # media_stream_ref를 직접 받아 검증·좁히므로, search가 고른 stream으로 다시
    # 명시적으로 부른다. 실제 로컬 영상(`register_local_source`로 등록된 source)에서는
    # media_stream_ref 없이는 이 호출 자체가 실패하므로, 첫 호출과 동일 인자를 그냥
    # 재사용하지 않는다. `_select_asset_span`은 fixture 경로(media_stream_ref를 줘도
    # recording이 spans[]를 자동으로 좁혀주지 않는 경로)에 대한 방어적 재확인으로 남긴다
    # — 실제 로컬 영상 경로는 recording이 이미 단일 span으로 narrowing해서 돌려주므로
    # 여기서는 no-op 확인이 된다.
    fine_resolution = rec_service.resolve_span(
        timeline_ref, requested_range, media_stream_ref=media_stream_ref
    )
    selected_span = _select_asset_span(fine_resolution, media_stream_ref)
    narrowed_resolution = fine_resolution.model_copy(update={"spans": [selected_span]})
    incident_clip = rec_service.build_incident_clip(
        narrowed_resolution.model_dump(mode="json")
    )

    read_request = readout_api.ReadRequest(
        case_id=case_id,
        candidate_id=candidate.candidate_id,
        input_ref=InputRef(
            incident_clip_ref=incident_clip.incident_clip_ref,
            source_profile="readout-native",
            provenance="SOURCE_DERIVED_INCIDENT_CLIP",
        ),
    )
    plate_run, plate_readout = readout_api.read_plate(
        read_request, provider=readout_providers.FixtureOcrProvider()
    )
    _overlay_run, overlay_readout = readout_api.read_overlay_time(
        read_request, provider=readout_providers.FixtureOcrProvider()
    )

    # 알려진 단순화 1 (모듈 docstring 참고) — recording이 아직 공개 함수로 노출 안 함.
    raw_recording = json.loads(
        (mock_root / "recording" / f"{SCENARIO_ID}.json").read_text(encoding="utf-8")
    )
    time_source_candidates = raw_recording.get("time_source_candidates", [])

    asset_refs = [facts.asset_ref for facts in fixture.asset_facts]
    asset_facts_real = [
        rec_service.lookup_asset_facts(ref).model_dump(mode="json") for ref in asset_refs
    ]

    return ObservationBundle(
        candidate=candidate,
        visual_evidence=visual_evidence,
        fine_run=fine_run,
        disposition=disposition,
        incident_clip=incident_clip.model_dump(mode="json"),
        plate_readout=plate_readout.to_dict() if plate_readout else None,
        overlay_readout=overlay_readout.to_dict() if overlay_readout else None,
        time_source_candidates=time_source_candidates,
        asset_facts=asset_facts_real,
        plate_read_outcome=plate_run.outcome,
    )


@dataclass
class RealVideoContext:
    """월요일 real 영상 실행 1건의 상태 — `RealVideoAdapter`가 `get_candidate_events()`와
    `get_evidence_record()` 사이에 들고 있어야 하는 것들. `prepare_real_video_context()`가
    만들고, `get_real_video_candidates()`/`build_evidence_for_real_video_candidate()`가
    재사용한다.

    호출자가 다 쓴 뒤(evidence 조립까지, search의 `open_analysis_source()` 소비도
    끝난 뒤) `rec_service.close()`해야 한다.
    """

    rec_service: RecordingService
    registered: Any
    timeline: Any
    scope: search_module.AnalysisScope
    gemini_service: Any
    analysis_source: Any
    bootstrap_ref: str
    local_video_path: str | Path


def prepare_real_video_context(
    *,
    local_video_path: str | Path,
    case: CaseAggregate,
    scope_id: str,
    target_event_types: list[str] | None = None,
) -> RealVideoContext:
    """`register_local_source()`부터 real Gemini/Elice service 조립까지 — candidate
    탐색 이전 단계. 이 단계는 candidate와 무관하게 한 번만 한다(전체 영상 범위
    AnalysisSource 하나 재사용 — 모듈 docstring 참고).

    `target_event_types`는 `scope.py`가 이미 명시한 대로("1차 구현 범위" —
    case에는 아직 intake UI가 이 값을 스스로 결정하는 로직이 없어 호출자가 그대로
    공급해야 한다) 호출자 책임이다. 생략하면 월요일 대표 영상용 값
    (`_MONDAY_TARGET_EVENT_TYPES`)으로 fallback한다 — 이건 계약 기본값이 아니라
    그 영상 하나를 위한 opaque 재사용값일 뿐이다(모듈 docstring 참고, 2026-09-23
    real_e2e_yt0002 실행에서 다른 영상엔 안 맞는다는 게 드러나 매개변수화함).
    """
    # 월요일 대표 파일(20260620_141956_EVT_1.avi) 기준 profile 설정 — 480p H.264,
    # preset=veryfast, crf=23, audio off(정철원 확인, 2026-09-21). canonical profile
    # 값 공간이 아니라 이번 실행 전용 opaque 설정이다(모듈 docstring 참고).
    profile_ref = f"prof_{uuid4().hex}"
    materializer = LocalAnalysisMaterializer(
        {profile_ref: AnalysisProfile(height=480, preset="veryfast", crf=23)}
    )
    # `build_incident_clip()`은 local source에 대해 analysis_materializer와 별도로
    # incident_materializer가 필요하다(recording/service.py:606) — 처음엔 이걸 몰라서
    # `LocalIncidentMaterializer` 없이 실행했다가 "실행 중인 단일 VIDEO 생성 설정이
    # 필요합니다"로 실패했다. 같은 인코딩 값을 재사용한다(모듈 docstring 참고 —
    # canonical 값이 아니라 이번 실행 전용).
    incident_materializer = LocalIncidentMaterializer(
        IncidentClipEncoding(height=480, preset="veryfast", crf=23)
    )
    rec_service = RecordingService(
        analysis_materializer=materializer, incident_materializer=incident_materializer
    )

    registered = rec_service.register_local_source(local_video_path)
    timeline = rec_service.create_relative_timeline(registered.source_asset.source_asset_ref)

    # 부트스트랩 stream 선택 — 정철원 확인(2026-09-21): 유일성 검증이지 임의 선택이
    # 아니다(모듈 docstring 참고).
    bootstrap_ref = _unique_video_media_stream_ref(registered.media_streams)

    duration_ms = int((registered.source_asset.duration_sec or 0) * 1000)
    if duration_ms <= 0:
        raise StreamSelectionError(
            "등록된 SourceAsset의 duration_sec을 확인할 수 없어 AnalysisScope 범위를"
            " 만들 수 없습니다."
        )
    whole_timeline_ref = {"timeline_id": timeline.timeline_id, "revision": timeline.revision}
    whole_requested_range = {"start_sec": 0.0, "end_sec": duration_ms / 1000}

    # coarse 검색용 AnalysisSource — 전체 영상 범위로 하나만 만든다. Fine 단계는
    # 같은 AnalysisSource를 candidate.span으로 좁혀서 재사용한다(search가 내부적으로
    # candidate.span 기준 clip을 만든다 — case가 후보별로 별도 AnalysisSource를
    # 다시 만들지 않는다). resolve_span은 로컬 등록 원본에서 media_stream_ref가
    # 항상 필수다.
    whole_resolution = rec_service.resolve_span(
        whole_timeline_ref, whole_requested_range, media_stream_ref=bootstrap_ref
    )
    whole_span = _select_asset_span(whole_resolution, bootstrap_ref)
    analysis_source = rec_service.prepare_analysis_source(
        whole_span.model_dump(mode="json"),
        profile_ref,
        timeline_ref=whole_timeline_ref,
    )

    scope_dict = build_analysis_scope(
        case,
        scope_id=scope_id,
        time_ranges=[
            {
                "kind": "TIMELINE_RELATIVE",
                "timeline_ref": {
                    "timeline_id": timeline.timeline_id,
                    "revision": timeline.revision,
                },
                "start_ms": 0,
                "end_ms": duration_ms,
            }
        ],
        target_event_types=target_event_types or _MONDAY_TARGET_EVENT_TYPES,
        max_cost_krw=_MONDAY_BUDGET["max_cost_krw"],
        max_latency_sec=_MONDAY_BUDGET["max_latency_sec"],
    )
    scope = search_module.AnalysisScope.model_validate(scope_dict)

    # search에 실제 Gemini/Elice service를 주입한다 — service=None이면
    # search_candidates()/verify_visual_with_stream_context()가 조용히 fixture로
    # 빠지므로, 여기서 명시적으로 real service를 만들어 넘긴다(모듈 docstring
    # "search에 실제 service 미주입 — 종결" 참고).
    env = load_env_file()
    api_key = env.get("GEMINI_API_KEY")
    if not api_key:
        raise StreamSelectionError(
            ".env에 GEMINI_API_KEY가 없습니다 — real Search 호출에 필요합니다."
        )
    analysis_source_ref = search_module.ContractRef(
        kind="analysis_source", ref=analysis_source.analysis_source_ref
    )
    resolver = RecordingAnalysisSourceResolver(
        scope_sources={scope.scope_id: (analysis_source_ref,)},
        ref_metadata={
            analysis_source.analysis_source_ref: SourceMeta(
                duration_sec=analysis_source.duration_sec,
                timeline_id=analysis_source.timeline_ref.timeline_id,
                timeline_revision=analysis_source.timeline_ref.revision,
            )
        },
        # rec_service가 open_analysis_source(ref) -> OpenedAnalysisSource를 이미
        # 갖고 있어 RecordingAnalysisSourceGateway 구조를 그대로 만족한다 — 별도
        # adapter 클래스가 필요 없다.
        gateway=rec_service,
    )
    gemini_service = search_module.build_gemini_search_service(
        api_key=api_key, resolver=resolver
    )

    return RealVideoContext(
        rec_service=rec_service,
        registered=registered,
        timeline=timeline,
        scope=scope,
        gemini_service=gemini_service,
        analysis_source=analysis_source,
        bootstrap_ref=bootstrap_ref,
        local_video_path=local_video_path,
    )


def get_real_video_candidates(
    context: RealVideoContext,
) -> tuple[search_module.CandidateEvent, ...]:
    """real Gemini/Elice **Coarse**를 실제로 호출한다(유료). `prepare_real_video_context()`가
    만든 `context`를 그대로 재사용 — candidate 탐색용 AnalysisSource를 다시 만들지
    않는다."""
    return run_real_video_candidate_search(context).candidates


def run_real_video_candidate_search(context: RealVideoContext) -> search_module.CandidateSearchResult:
    """real Coarse(유료) 결과 전체 — `AnalysisRun.outcome`까지 보존한다. 실패 Run은 후보 0개라
    후보만 보면 「찾았지만 없음」과 구분되지 않는다(PR #187 리뷰)."""
    return search_module.search_candidates(context.scope, service=context.gemini_service)


def _build_ocr_provider(context: RealVideoContext) -> paddle_provider.PaddleOcrProvider:
    """실영상 번호판·시각 판독용 PaddleOCR — IncidentClip 구간 프레임을 recording에서 받는다.

    `RecordingFrameSource`는 clip 길이 기준 샘플 지점을 recording이 발급한 `FrameRef`와 PNG로
    받아 온다. 원본 파일 경로를 readout에 넘기지 않는다(공개 계약 안에서만 접근).
    """
    return paddle_provider.PaddleOcrProvider(
        paddle_provider.RecordingFrameSource(context.rec_service)
    )


def build_evidence_for_real_video_candidate(
    context: RealVideoContext,
    candidate: search_module.CandidateEvent,
    *,
    case_id: str,
    selection_rev: int = 1,
    correction_records: list[dict[str, Any]] | None = None,
    location_hint: str | None = None,
    on_visual_result: Any = None,
) -> EvidenceBundle:
    """선택된 candidate 하나에 대해 real Gemini/Elice **Fine**을 실제로 호출하고
    (유료) IncidentClip~evidence까지 조립한다. `case.select_candidate()`가 고른
    candidate를 그대로 받는다 — 여기서 다시 고르지 않는다.

    `observe_real_video_candidate()` + `assemble_evidence_bundle()`을 이어 부른다. 정정 후
    다시 계산할 때는 관찰 결과를 재사용하고 조립만 다시 부른다(이슈 #73, `RealVideoAdapter`).
    `on_visual_result`는 `observe_real_video_candidate()`로 그대로 전달된다.
    """
    observations = observe_real_video_candidate(
        context, candidate, case_id=case_id, on_visual_result=on_visual_result
    )
    return assemble_evidence_bundle(
        observations,
        case_id=case_id,
        selection_rev=selection_rev,
        correction_records=correction_records,
        location_hint=location_hint,
    )


def observe_real_video_candidate(
    context: RealVideoContext,
    candidate: search_module.CandidateEvent,
    *,
    case_id: str,
    on_visual_result: Any = None,
) -> ObservationBundle:
    """`build_evidence_for_real_video_candidate()`의 관찰 단계 — real Fine(유료) →
    IncidentClip → PaddleOCR → 시간 source·AssetFacts까지. 정정과 무관한 값만 만든다.

    `on_visual_result`는 `(visual_result, media_stream_ref)`를 받는 선택적
    콜백이다 — Fine 응답을 실제로 받은 **직후**, 이후 단계(IncidentClip·readout·
    evidence 조립)가 실패하기 **전에** 호출된다. 유료 응답을 downstream 버그로
    잃지 않고 캡처해 재사용(replay)하려는 용도다(이슈 #135/#137 진단 과정에서
    필요성이 드러남) — real_e2e.py 자체는 여기서 아무것도 저장하지 않는다.
    """
    rec_service = context.rec_service
    registered = context.registered
    analysis_source = context.analysis_source
    bootstrap_ref = context.bootstrap_ref
    scope = context.scope

    visual_result, media_stream_ref = _resolve_via_search_stream_context(
        analysis_source=analysis_source,
        media_streams=registered.media_streams,
        candidate=candidate,
        target_hint=scope.hint,
        service=context.gemini_service,
    )
    if on_visual_result is not None:
        on_visual_result(visual_result, media_stream_ref)
    # 정철원 확인(2026-09-21) — 월요일 대표 파일은 VIDEO가 하나뿐이라 search가
    # 부트스트랩과 다른 stream을 고를 수 없다. 다르면 조용히 넘어가지 않고 실패시켜
    # 배선 버그를 표면화한다.
    if media_stream_ref != bootstrap_ref:
        raise StreamSelectionError(
            f"search 실행 문맥이 돌려준 media_stream_ref({media_stream_ref!r})가"
            f" 부트스트랩 ref({bootstrap_ref!r})와 다릅니다 — 월요일 대표 파일은"
            " VIDEO가 하나뿐이라 항상 같아야 합니다."
        )

    visual_evidence = visual_result.visual_evidence.model_dump(mode="json")
    fine_run = visual_result.analysis_run.model_dump(mode="json")

    # Fine 결과를 downstream(두 번째 resolve_span·IncidentClip·readout·TimeResolution
    # 포함)으로 밀어넣기 전에 먼저 분류한다(이슈 #137, `build_happy_001_evidence_bundle()`과
    # 동일 패턴 — PR #131→#142 후속 정합화). `NOT_OBSERVED`는 유효한 관찰 결과이므로
    # 여기서 조립을 시작하지 않고 정상 종료한다.
    disposition = classify_visual_evidence(visual_evidence)
    if disposition.decision == NOT_ASSEMBLED:
        return ObservationBundle(
            candidate=candidate,
            visual_evidence=visual_evidence,
            fine_run=fine_run,
            disposition=disposition,
        )

    # 두 번째 resolve_span() — IncidentClip은 전체 영상이 아니라 candidate.span만큼
    # 좁혀야 한다(evidence가 실제로 볼 clip이라서 coarse의 전체 범위와 다르다).
    timeline_ref = {
        "timeline_id": candidate.span.timeline_id,
        "revision": candidate.span.timeline_revision,
    }
    requested_range = {
        "start_sec": candidate.span.start_ms / 1000,
        "end_sec": candidate.span.end_ms / 1000,
    }
    fine_resolution = rec_service.resolve_span(
        timeline_ref, requested_range, media_stream_ref=media_stream_ref
    )
    selected_span = _select_asset_span(fine_resolution, media_stream_ref)
    narrowed_resolution = fine_resolution.model_copy(update={"spans": [selected_span]})
    incident_clip = rec_service.build_incident_clip(
        narrowed_resolution.model_dump(mode="json")
    )

    read_request = readout_api.ReadRequest(
        case_id=case_id,
        candidate_id=candidate.candidate_id,
        input_ref=InputRef(
            incident_clip_ref=incident_clip.incident_clip_ref,
            source_profile="readout-native",
            provenance="SOURCE_DERIVED_INCIDENT_CLIP",
        ),
    )
    ocr_provider = _build_ocr_provider(context)
    plate_run, plate_readout = readout_api.read_plate(read_request, provider=ocr_provider)
    _overlay_run, overlay_readout = readout_api.read_overlay_time(
        read_request, provider=ocr_provider
    )

    # 실제 시간 source — recording의 observe_time_sources()가 이제 develop에 있다
    # (#129). filename/metadata에서 관찰된 값을 그대로 evidence에 넘긴다 — case가
    # 신뢰도나 값을 재해석하지 않는다.
    observed_time_sources = rec_service.observe_time_sources(
        registered.source_asset.source_asset_ref
    )
    time_source_candidates = [
        c.model_dump(mode="json") for c in observed_time_sources.candidates
    ]

    # 알려진 단순화(모듈 docstring) — `lookup_asset_facts()`는 로컬로 materialize된
    # analysis_source/incident_clip에 대해서는 AssetFacts를 등록하지 않는다
    # (`RecordingService.prepare_analysis_source()`/`build_incident_clip()`의 로컬
    # 경로가 `add_asset_facts()`를 안 부름 — recording 쪽 gap, 실행해보고 발견함).
    # `source_asset`만 `inspect_local_source()`로 즉석 조회가 된다. fixture 경로도
    # 원래 `analysis_source`는 asset_facts에 안 넣는다(happy_001 fixture 확인) — 이
    # 부분은 fixture와 다르지 않다.
    asset_facts_real = [
        rec_service.lookup_asset_facts(
            {"kind": "source_asset", "ref": registered.source_asset.source_asset_ref}
        ).model_dump(mode="json"),
    ]
    return ObservationBundle(
        candidate=candidate,
        visual_evidence=visual_evidence,
        fine_run=fine_run,
        disposition=disposition,
        incident_clip=incident_clip.model_dump(mode="json"),
        plate_readout=plate_readout.to_dict() if plate_readout else None,
        overlay_readout=overlay_readout.to_dict() if overlay_readout else None,
        time_source_candidates=time_source_candidates,
        asset_facts=asset_facts_real,
        plate_read_outcome=plate_run.outcome,
    )


def build_real_video_evidence_bundle(
    *,
    case_id: str,
    local_video_path: str | Path,
    case: CaseAggregate,
    scope_id: str,
    selection_rev: int = 1,
    correction_records: list[dict[str, Any]] | None = None,
    location_hint: str | None = None,
    on_visual_result: Any = None,
    target_event_types: list[str] | None = None,
) -> tuple[EvidenceBundle, RecordingService]:
    """`prepare_real_video_context()` + `get_real_video_candidates()`(candidates[0]
    고정) + `build_evidence_for_real_video_candidate()`를 한 번에 묶은 편의 함수 —
    `case.select_candidate()` 없이 단일 실행으로 스모크하는 스크립트용이다
    (`docs/modules/case/experiments/real-e2e-20260922-monday-baseline.md` 참고).

    `RealVideoAdapter`처럼 candidate 선택을 case 상태 기계에 맡기려면 이 함수
    대신 위 3개를 직접 조합해서 쓴다. `on_visual_result`는
    `build_evidence_for_real_video_candidate()`로 그대로 전달된다(같은 docstring
    참고).
    """
    context = prepare_real_video_context(
        local_video_path=local_video_path,
        case=case,
        scope_id=scope_id,
        target_event_types=target_event_types,
    )
    candidates = get_real_video_candidates(context)
    if not candidates:
        raise StreamSelectionError(
            "월요일 대표 영상에서 candidate가 하나도 나오지 않았습니다 — GT 없는"
            " 배관 확인이 목적이라 이 경우를 자동으로 처리하지 않는다."
        )
    # 알려진 단순화(모듈 docstring 참고) — candidate가 여럿이면 어느 것이 맞는지는
    # 이번 범위 밖이라 첫 번째를 그대로 쓴다.
    candidate = candidates[0]
    bundle = build_evidence_for_real_video_candidate(
        context,
        candidate,
        case_id=case_id,
        selection_rev=selection_rev,
        correction_records=correction_records,
        location_hint=location_hint,
        on_visual_result=on_visual_result,
    )
    return bundle, context.rec_service
