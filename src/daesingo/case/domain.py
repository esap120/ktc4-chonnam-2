"""Case 애그리게잇 — 5-state 상태 기계 + selection_rev 내부 저장.

근거:
  - 상태 기계: `docs/architecture/module-architecture.md` §4-모듈5 ②
  - selection_rev 단일 현재값 저장(별도 이력 테이블 없음):
    `docs/modules/case/decisions/case-selection-revision-persistence.md` (2026-09-13)
  - CaseView에는 절대 selection_rev를 노출하지 않는다(위 결정 그대로) — `view.py` 참고.

⚠️ 역행 전이 구현 범위(2026-09-14 갱신): `module-architecture.md` §4-모듈5 ②는 "`TIME_HINT_EDIT`,
major `TIMELINE_REBASE`, candidate 변경 등에 의해 뒤 단계에서 앞 단계로 돌아갈 수 있다"고만
적어뒀지만, `docs/modules/case/doc-research/부분 재실행 정책 표 초안 v1...md`(연구 메모, 9개
`CorrectionRecord.kind` 각각의 stage 전이/재실행/폐기/보존을 표로 완성해둠)가 이 한 줄을
구체화한다. 그 표 기준으로 실제 구현 가능한 것과 막힌 것을 나눴다:
  - `TIME_HINT_EDIT` — 표 1행 그대로 `SEARCHING`으로 역행(`regress_to_searching()`). case가
    소유한 순수 workflow state라 case 혼자 구현 가능.
  - `OTHER_CANDIDATE`("candidate 변경") — 표 2행을 보면 실제로는 역행이 **아니다**: 뒤 단계
    (`EVIDENCE_REVIEW`)에 "제자리"로 머문다(`reselect_candidate()`). §4-모듈5 ②의 "candidate
    변경"이라는 표현이 역행을 뜻하는 것처럼 읽히지만, 더 구체적인 이 연구 메모가 실제로는
    아니라고 정정한다 — 문서 간 불일치이며 원문(module-architecture.md)을 고치는 건 이 세션
    범위 밖이라 그대로 뒀다(2026-09-14 체크리스트 §11 노트 참고).
  - major `TIMELINE_REBASE` — 표 맨 아래 자체가 "신유민(web)이랑 화면 흐름 확인 안 하면 나
    혼자 추천하기 어려운 지점"이라고 명시한다. 접합부 문제라 이번에도 구현하지 않는다.
  - 나머지 6개 kind(`PLATE_MANUAL_EDIT`/`PLATE_REREAD`/`SPAN_ADJUST`/`REPORT_TYPE_CHANGE`/
    `EVENT_TIME_MANUAL`/`SITUATION_CHANGE`)는 표에서도 stage 전이가 "제자리"라 별도 domain
    메서드가 필요 없다 — `correction.apply_correction()` 하나로 이미 충분하다.
  - 실제 fixture로 검증된 게 아니라 이 연구 메모(초안, `decisions/`로 승격되지 않음)를 근거로
    case가 스스로 설계해 구현한 것이므로, 표시(`[x]`)에도 그 구분을 그대로 남긴다
    (`phase1-completion-checklist.md` §3-B).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STAGES = (
    "INTAKE",
    "SEARCHING",
    "CANDIDATE_REVIEW",
    "EVIDENCE_REVIEW",
    "READY",
)

# 전진 전이만 1차로 구현한다. 역행 전이는 §11 제외 범위.
_FORWARD_EDGES: dict[str, str] = {
    "INTAKE": "SEARCHING",
    "SEARCHING": "CANDIDATE_REVIEW",
    "CANDIDATE_REVIEW": "EVIDENCE_REVIEW",
    "EVIDENCE_REVIEW": "READY",
}


class InvalidTransition(Exception):
    pass


class SourceNotAccepted(Exception):
    """원본 연결은 `INTAKE`에서만 받는다(8-17 case 쪽) — 분석 시작 뒤 추가 업로드는 거부한다.
    HTTP status · code는 HTTP API Contract가 정한다."""


# 빈 case의 초기값(HTTP API Contract §5.1 예시) — `decisions/empty-case-and-manifest.md`.
_EMPTY_HINTS = ("time", "vehicle", "situation", "location")
_EMPTY_MANIFEST = {"file_count": 0, "ok_file_count": 0, "failed_file_count": 0, "duration_sec": 0, "range": None}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_SITUATION_RESPONSE_VALUES = frozenset({"CONFIRMED", "CORRECTED", "USER_UNSURE"})


@dataclass
class Candidate:
    candidate_id: str
    at: str | None
    at_provenance: str | None
    observed: str
    thumb_ref: str | None
    selected: bool = False
    timeline_revision: int = 1
    stale_revision: bool = False
    stale_revision_label_key: str | None = None
    situation_confirmation: str = "NOT_ASKED"
    # search `CandidateEvent.rank`(Run 안의 순위, 1부터) 그대로. case가 다시 매기지 않는다(#122).
    rank: int | None = None
    # search `CandidateEvent.span.representative_ms`(그 후보 timeline revision 기준 상대 ms) 그대로.
    # CaseView `candidates[].marker_ms`의 원천이다(#184). case가 계산·보정하지 않는다.
    representative_ms: int | None = None
    # 저장된 상태에 있었지만 이 코드가 모르는 키(새 코드가 쓴 필드). 다시 저장할 때 그대로 쓴다 —
    # rollback한 옛 코드가 새 필드를 지우지 않게(`decisions/case-store-mysql.md` §4).
    extra: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


# JobRecord 정산 사유 — case가 그 job의 결과를 더 기다리지 않게 된 이유(`decisions/running-jobs-derivation.md`).
JOB_SETTLE_REASONS = ("REFLECTED", "STOPPED_WAITING", "CANCELLED", "SUPERSEDED")


@dataclass
class CaseAggregate:
    """case가 소유하는 내부 상태. `CaseView`는 이 상태 + 다른 모듈 산출물의 projection이다
    (module-architecture.md §4-모듈5 ⑥) — 이 클래스 자체를 밖으로 노출하지 않는다.
    """

    case_id: str
    case_rev: int = 1
    stage: str = "INTAKE"
    user_reviewed: bool = False
    hints: dict[str, Any] = field(default_factory=dict)
    manifest_summary: dict[str, Any] = field(default_factory=dict)

    # selection_rev — 단일 현재값. 이력 테이블 없음(2026-09-13 결정). CaseView 비노출.
    selection_rev: int = 0

    candidates: list[Candidate] = field(default_factory=list)
    job_records: list[dict[str, Any]] = field(default_factory=list)
    correction_records: list[dict[str, Any]] = field(default_factory=list)

    # 사용자의 신고 상황 응답 — `EvidenceRecord.situation_response`와 같은 모양
    # (`value`·`responded_at`·`candidate_ref`). 응답 전에는 `None`(= CaseView `NOT_ASKED`)이며,
    # 무응답을 `USER_UNSURE`로 만들지 않는다(#171 B-2, 통합 항목 I1).
    situation_response: dict[str, Any] | None = None

    # 마지막 후보 탐색(CANDIDATE_SEARCH Run)이 실패했는가. 실패 Run은 후보 0개라 「찾았지만 없음」과
    # 구분하려면 이 사실이 따로 필요하다(PR #187 리뷰). 다음 탐색이 성공하면 지운다.
    candidate_search_failed: bool = False

    # 후보 목록 세대 — `receive_candidates()`가 목록을 교체하거나 `regress_to_searching()`이 비울 때마다
    # 오른다. adapter는 같은 세대 안에서만 후보별 관찰(Fine·판독)을 재사용한다
    # (`decisions/reselect-observation-reuse.md`). `selection_rev`와 달리 재선택으로는 오르지 않는다. CaseView 비노출.
    candidate_generation: int = 0

    # COARSE_SEARCH가 쓴 AnalysisScope(`scope_id` → scope). JobRecord는 `scope_ref`만 들고 있어, process가
    # 바뀌어도 scope를 다시 읽을 수 있게 aggregate에 남긴다(#246 S-4). CaseView 비노출. scope는 불변.
    analysis_scopes: dict[str, dict[str, Any]] = field(default_factory=dict)

    # case가 더는 결과를 기다리지 않는 job(`job_id` → `JOB_SETTLE_REASONS` 중 하나). `running_jobs[]`는
    # 여기 없는 JobRecord다(계약 B§10 불변조건 5). 처음 사유가 이긴다. CaseView 비노출.
    settled_jobs: dict[str, str] = field(default_factory=dict)

    # 분석 시작 때 사용자가 적은 설명 원문(case-command Draft §11). 받은 그대로 두고 CaseView `description`으로
    # 내린다. 분석 시작 전에는 `None`.
    description: str | None = None

    # 처리 가능한 등록 원본(등록 순서) — `{source_asset_ref, video_stream_ref, duration_sec}`. 분석 시작이 타임라인을
    # 만들 입력이다(`decisions/start-analysis.md` §3-1). `video_stream_ref`는 등록 때 VIDEO가 정확히 하나였을 때만
    # 있다 — case가 여러 VIDEO 중 하나를 고르지 않는다. CaseView 비노출.
    sources: list[dict[str, Any]] = field(default_factory=list)

    # 저장된 상태의 모르는 최상위 키 — `Candidate.extra`와 같은 이유. CaseView 비노출.
    extra_state: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def intake(cls, case_id: str, hints: dict[str, Any], manifest_summary: dict[str, Any]) -> "CaseAggregate":
        """hints · manifest를 한 번에 받는 진입점 — fixture · 테스트 경로용. 제품 진입점은 빈 case를 만드는
        `service.create_case()`이고, 원본은 `record_source_registered()`로 하나씩 들어온다."""
        return cls(case_id=case_id, stage="INTAKE", hints=dict(hints), manifest_summary=dict(manifest_summary))

    @classmethod
    def empty(cls, case_id: str) -> "CaseAggregate":
        return cls(
            case_id=case_id,
            stage="INTAKE",
            hints={key: None for key in _EMPTY_HINTS},
            manifest_summary=dict(_EMPTY_MANIFEST),
        )

    def record_source_registered(
        self, source_asset: dict[str, Any], media_streams: list[dict[str, Any]] | None = None
    ) -> None:
        """recording이 등록 · 연결한 원본 1개를 `manifest_summary`에 센다.

        `file_count` +1, `availability=AVAILABLE`이면 `ok_file_count` +1. `failed_file_count`(의미 미결) ·
        `duration_sec`(「전체 구간 길이」 — 전방 · 후방이 같은 시간대를 찍으면 합산이 틀린다) · `range`는
        recording timeline 몫이라 여기서 계산하지 않는다. `case_rev`는 올리지 않는다 — 이후 판단의 입력이
        아니고, 동시 업로드 응답이 뒤섞여도 분석 시작이 `stale_revision`에 걸리지 않게.

        처리 가능한 원본은 `sources`에도 남긴다 — VIDEO 스트림이 정확히 하나면 그 ref, 아니면 `None`
        (`decisions/start-analysis.md` §3-1).
        """
        if self.stage != "INTAKE":
            raise SourceNotAccepted(f"원본 연결은 INTAKE에서만 받는다: stage={self.stage}")
        self.manifest_summary["file_count"] += 1
        if source_asset.get("availability") == "AVAILABLE":
            self.manifest_summary["ok_file_count"] += 1
            videos = [s["media_stream_ref"] for s in media_streams or [] if s.get("media_type") == "VIDEO"]
            self.sources.append(
                {
                    "source_asset_ref": source_asset["source_asset_ref"],
                    "video_stream_ref": videos[0] if len(videos) == 1 else None,
                    "duration_sec": source_asset.get("duration_sec"),
                }
            )

    def record_analysis_scope(self, scope: dict[str, Any]) -> None:
        """scope는 불변이다 — 같은 `scope_id`로 다른 내용이 오면 거부한다."""
        scope_id = scope["scope_id"]
        if not isinstance(scope_id, str) or not scope_id or len(scope_id) > 128 or not scope_id.isascii():
            raise ValueError(f"scope_id는 1~128자 ASCII 문자열이어야 한다: {scope_id!r}")
        existing = self.analysis_scopes.get(scope_id)
        if existing is not None and existing != scope:
            raise ValueError(f"AnalysisScope는 바꿀 수 없다: {scope_id!r}")
        self.analysis_scopes[scope_id] = dict(scope)

    def _advance(self, expected_from: str, to: str, *, bump_case_rev: bool = True) -> None:
        if self.stage != expected_from:
            raise InvalidTransition(f"{self.stage} -> {to} (expected from {expected_from})")
        if _FORWARD_EDGES.get(self.stage) != to:
            raise InvalidTransition(f"{self.stage} -> {to} 는 등록된 전진 전이가 아니다")
        self.stage = to
        if bump_case_rev:
            self.case_rev += 1

    def start_search(self) -> None:
        # scenario_happy_001의 case_views[0](stage=SEARCHING)이 case_rev:1 그대로인 것과
        # job_h001_search(COARSE_SEARCH)의 case_rev:1을 근거로, INTAKE→SEARCHING은
        # case_rev를 올리지 않는다 — "요청 시점 케이스 리비전"은 아직 바뀔 내용이 없다.
        self._advance("INTAKE", "SEARCHING", bump_case_rev=False)

    def record_extracted_hints(self, hints: dict[str, str | None]) -> None:
        """단서 구조화(`HINT_EXTRACT`) 결과로 `hints`를 바꾼다. 결과는 분석 시작 직후 탐색 발주 전에만
        들어오므로 `SEARCHING` 전용이다. 사용자 요청이 아니라 실행 결과라 `case_rev`를 올리지 않는다
        (`record_candidate_search_failure()`와 같다). 어떤 값을 넣을지(매핑 · 실패 처리)는
        `analysis_start.hints_from_result()`가 정한다."""
        if self.stage != "SEARCHING":
            raise InvalidTransition(f"{self.stage}에서는 단서 구조화 결과를 받을 수 없다(SEARCHING 전용)")
        self.hints = dict(hints)

    def record_candidate_search_failure(self) -> None:
        """후보 탐색 Run이 `FAILED`로 끝났다. 계약 §7(`RESUME_SEARCH` 행): 실패 Run은 투영 대상을
        바꾸지 않는다 — 후보 목록을 교체하지 않고, `CANDIDATE_REVIEW`로 진행하지도 않는다(그러면
        web이 「결과 없음」으로 그린다). stage는 `SEARCHING`에 머물고 실패 사실만 남긴다.
        실패는 사용자 요청이 아니라 실행 결과라 `case_rev`를 올리지 않는다(§3-E)."""
        if self.stage != "SEARCHING":
            raise InvalidTransition(f"{self.stage}에서는 후보 탐색 실패를 받을 수 없다(SEARCHING 전용)")
        self.candidate_search_failed = True
        self._reflect_waiting("COARSE_SEARCH")

    def receive_candidates(self, candidates: list[Candidate]) -> None:
        """빈 배열(candidates=[])은 실패가 아니다 — `scenario_empty_001` 원칙(2026-09-14,
        실제 fixture로 검증: `AnalysisRun.outcome=SUCCEEDED`+`candidates=[]`도 검색 자체는
        성공이므로 `CANDIDATE_REVIEW`로 전진한다). 빈 배열이든 아니든 전진 여부는 같고,
        차이는 이후 단계(선택 가능한 candidate가 없어 evidence 파이프라인이 발주되지 않음)와
        `CaseView.notices[]`(`search.no_candidates`, 비차단 INFO)에서만 갈린다 — 이 notice는
        CaseView 값(`CANDIDATE_REVIEW` + 빈 `candidates`)만으로 발동해 `service.derive_notices()`가
        붙인다."""
        self.candidates = list(candidates)
        self.candidate_generation += 1
        self.candidate_search_failed = False
        self._advance("SEARCHING", "CANDIDATE_REVIEW")
        self._reflect_waiting("COARSE_SEARCH")

    def select_candidate(self, candidate_id: str) -> None:
        """후보 선택은 case 소유(ownership.md §6) — evidence는 참조만 하고 복사해 갖지 않는다.
        selection_rev는 오르지만 case_rev는 오르지 않는다(2026-09-14, `scenario_correction_rerun_001`/
        `scenario_plate_reread_001` fixture로 정정 — 이전엔 이 전이도 case_rev를 올린다고
        잘못 가정했었다). candidate 선택은 "검색 결과를 검토하는" 같은 흐름의 연장이지 그
        자체로 새 요청이 아니라서, case_rev는 다음 실제 요청(재판독 발주·정정 제출 등,
        §3-E)에서 처음 오른다."""
        match = next((c for c in self.candidates if c.candidate_id == candidate_id), None)
        if match is None:
            raise InvalidTransition(f"알 수 없는 candidate_id: {candidate_id}")
        for c in self.candidates:
            c.selected = c.candidate_id == candidate_id
        self.selection_rev += 1
        self.situation_response = None
        self._advance("CANDIDATE_REVIEW", "EVIDENCE_REVIEW", bump_case_rev=False)

    def select_top_ranked(self) -> str | None:
        """가장 유력한 후보(`rank=1`)를 자동 선택한다(core-user-flow §8-1, #168 결정 1).

        case가 들고 있는 후보는 최근 `CANDIDATE_SEARCH` Run의 것이라(#168 결정 2, `receive_candidates()`가
        목록을 교체한다) 그 안의 `rank=1`이 곧 최근 Run의 rank1이다. stale이면(과거 timeline
        revision 기준) 고르지 않는다 — 최신 후보가 아니면 가장 유력한 후보를 임의로 정하지 않는다
        (§8). 후보가 없거나 고를 수 없으면 `None`이고 stage는 그대로다.
        """
        top = next((c for c in self.candidates if c.rank == 1), None)
        if top is None or top.stale_revision:
            return None
        self.select_candidate(top.candidate_id)
        return top.candidate_id

    def mark_ready(self, *, report_package: dict[str, Any] | None) -> None:
        """`READY` = `PACKAGE_READY` 파생 gate 성립 시점(CaseView 계약 B절, #171 C). ReportPackage는
        ready-only라 존재 자체가 FINAL `PASS`/`WARN`의 증거다 — 없으면 전이를 거부한다(#167).
        downstream 스냅샷에서 판단하는 호출자는 `service.mark_ready_if_package_ready()`를 쓴다."""
        if report_package is None:
            raise InvalidTransition("READY는 준비된 ReportPackage 없이 들어갈 수 없다(#167)")
        self._advance("EVIDENCE_REVIEW", "READY")

    def bump_revision(self) -> None:
        """단계 전이 없이도 `case_rev`가 오르는 경우를 위한 범용 훅.

        `case_rev`는 "요청 시점 케이스 리비전"(§3-E)이지 stage 전이 전용 카운터가 아니다 —
        `scenario_plate_reread_001` fixture로 확인됨: 번호판 재판독으로 `EvidenceRecord`가
        v1→v2로 supersede될 때 stage는 `EVIDENCE_REVIEW`에 그대로 머무는데 `case_rev`는
        3→4로 오른다. `_advance()`와 달리 전이 유효성 검사를 하지 않는 단순 카운터 증가라,
        stage 전이가 아닌 사유로 case_rev를 올려야 하는 지점(증거 supersede 등)에서 직접
        호출한다. `mark_reviewed()`도 내부적으로 이걸 쓴다.
        """
        self.case_rev += 1

    def mark_reviewed(self) -> None:
        """`USER_REVIEWED` 상태 전환 — `CaseView.stage`가 아니라 별도 boolean으로 관리한다
        (`ownership.md` §7-③ 종결 사항). `scenario_happy_001` fixture로 확인됨: rev3(READY,
        `case_rev:3`, `user_reviewed:false`)→rev4(READY, `case_rev:4`, `user_reviewed:true`)로,
        stage는 그대로 READY인데 사용자가 최종 패키지를 확인했다는 새 요청이라 case_rev가
        오른다(이전엔 이 지점을 "package 최초 완성"으로 잘못 추정했었다 — 실제로는 package는
        rev3에서 이미 동일했고 `user_reviewed`만 바뀐다)."""
        self.user_reviewed = True
        self.bump_revision()

    def check_regress_to_searching(self) -> None:
        """`TIME_HINT_EDIT` 역행을 받아도 되는지 **아무것도 바꾸지 않고** 검사한다(`check_reselect()`와
        같은 원칙, #166). `correction.edit_time_hint()`가 CorrectionRecord를 남기기 전에 먼저 부른다 —
        예전엔 기록·`hints`·`case_rev`를 먼저 바꾼 뒤 역행이 거부돼 그것들만 남았다(탐색 실패로
        `SEARCHING`에 머문 case, orchestration 지표 4차 측정)."""
        if self.stage not in ("CANDIDATE_REVIEW", "EVIDENCE_REVIEW", "READY"):
            raise InvalidTransition(f"{self.stage}에서는 SEARCHING으로 역행할 수 없다")

    def regress_to_searching(self) -> None:
        """`TIME_HINT_EDIT` 역행 전이 — `CANDIDATE_REVIEW`/`EVIDENCE_REVIEW`/`READY` 중 어디서든
        `SEARCHING`으로 되돌아간다(`부분 재실행 정책 표 초안` 1행: "다시 도는 것=1차 탐색,
        폐기되는 것=후보·2차확인·선택·증거, 절대 안 건드리는 것=시간축·원본"). case가 들고
        있는 것 중 "폐기" 대상은 `candidates`뿐이다(2차 확인/증거는 evidence 쪽 데이터라 case가
        아예 갖고 있지 않다 — 애초에 지울 게 없다). `selection_rev`는 건드리지 않는다(과거
        correction_records가 스냅샷해 둔 값과의 정합성을 깨지 않기 위해 — 단조 증가만 유지).

        `case_rev`는 여기서 올리지 않는다 — 이 메서드를 부르는 `correction.edit_time_hint()`가
        `apply_correction()`으로 이미 한 번 올린다(한 사용자 요청 = 한 case_rev 증가, §3-E).
        """
        self.check_regress_to_searching()
        self.stage = "SEARCHING"
        self.candidates = []
        self.candidate_generation += 1

    def check_reselect(self, candidate_id: str) -> None:
        """`OTHER_CANDIDATE`를 받아도 되는지 **아무것도 바꾸지 않고** 검사한다(#166).

        `correction.reselect_candidate()`가 CorrectionRecord를 남기기 전에 먼저 부른다 — 예전엔
        기록을 먼저 남긴 뒤 domain이 거부해 `case_rev`·CorrectionRecord만 남는 불일치가 있었다.
        허용 stage는 `EVIDENCE_REVIEW`와 `READY`(#173 E-4: 결과 화면에서도 다른 후보 선택 허용).
        이미 선택된 후보를 다시 고르는 것은 값이 바뀌지 않는 요청이라 거부한다
        (correction-record §8-7: 무변경 입력은 기록하지 않는다).
        """
        if self.stage not in ("EVIDENCE_REVIEW", "READY"):
            raise InvalidTransition(
                f"{self.stage}에서는 OTHER_CANDIDATE 재선택을 쓸 수 없다(EVIDENCE_REVIEW·READY 전용)"
            )
        match = next((c for c in self.candidates if c.candidate_id == candidate_id), None)
        if match is None:
            raise InvalidTransition(f"알 수 없는 candidate_id: {candidate_id}")
        if match.selected:
            raise InvalidTransition(f"이미 선택된 candidate_id다: {candidate_id}")

    def reselect_candidate(self, candidate_id: str) -> None:
        """`OTHER_CANDIDATE` — 이미 선택을 마친 뒤 사용자가 "다른 후보가 맞다"고 정정하는 경로.
        `selected` 플래그를 새 candidate로 옮기고, 새 선택 context를 나타내려고 `selection_rev`를
        올린다(`case-selection-revision-persistence.md`). 최초 선택(`select_candidate()`,
        `CANDIDATE_REVIEW`→`EVIDENCE_REVIEW` 전이 포함)과는 다른 메서드다.

        `EVIDENCE_REVIEW`에서는 제자리에 머문다(`부분 재실행 정책 표 초안` 2행). `READY`에서는
        새 초안을 준비해야 하므로 `EVIDENCE_REVIEW`로 돌아간다 — 이전 Package로 handoff하지
        않는다(#173 E-4). 어느 쪽이든 이전 초안의 최종 검토(`user_reviewed`)는 새 초안의 확인이
        아니므로 되돌린다(#173 값별 경계표). `case_rev`는 여기서 올리지 않는다 —
        `correction.reselect_candidate()`가 `apply_correction()`으로 이미 올린다."""
        self.check_reselect(candidate_id)
        for c in self.candidates:
            c.selected = c.candidate_id == candidate_id
        self.selection_rev += 1
        # 응답은 선택된 candidate에 묶인다(`candidate_ref`) — 새 후보에 대해서는 다시 묻는다.
        self.situation_response = None
        self.user_reviewed = False
        if self.stage == "READY":
            self.stage = "EVIDENCE_REVIEW"

    def record_situation_response(self, value: str, *, responded_at: str) -> dict[str, Any]:
        """결과 화면 「신고 상황」 항목에서 사용자가 실제로 누른 응답을 기록한다(#171 B-2 ·
        통합 항목 I1). `value`는 `CONFIRMED`(맞아요)·`CORRECTED`(다른 상황)·`USER_UNSURE`
        (잘 모르겠어요) 중 하나이고, `candidate_ref`는 지금 선택된 candidate다.

        새 사용자 요청이라 `case_rev`를 올린다(§3-E) — adapter는 이를 보고 evidence를 다시
        조립한다(관찰 결과는 재사용, 이슈 #73). `CORRECTED`에 필요한 `SITUATION_CHANGE`
        CorrectionRecord 존재 여부는 evidence가 조립 시 검증한다.
        """
        if value not in _SITUATION_RESPONSE_VALUES:
            raise ValueError(f"알 수 없는 situation_response 값: {value!r}")
        selected = next((c for c in self.candidates if c.selected), None)
        if selected is None:
            raise InvalidTransition("선택된 candidate가 없어 신고 상황 응답을 기록할 수 없다")
        self.situation_response = {
            "value": value,
            "responded_at": responded_at,
            "candidate_ref": {"kind": "candidate_event", "ref": selected.candidate_id},
        }
        self.leave_ready()
        self.bump_revision()
        return dict(self.situation_response)

    def leave_ready(self) -> None:
        """다시 조립되는 변경(값 정정·상황 응답)이 오면 `READY`에서 `EVIDENCE_REVIEW`로 내린다.

        `READY`는 `PACKAGE_READY` 파생 gate이고(CaseView 계약 §10-9: READY면 FINAL이 PASS/WARN),
        재조립 뒤에도 성립하는지는 새 결과를 봐야 안다 — 내리지 않으면 Package가 사라져도
        `READY`로 남는다(orchestration 지표 4차 측정 I1). 상태 기계 설계 초안 v1 §3 「READY에서
        어떤 정정이 들어와도 package는 즉시 무효화」. 성립하면 command의 성공 뒤 재확인이 다시
        올린다(case-command 계약 §5).

        `user_reviewed`는 건드리지 않는다 — 필드 수정과 별개다(계약 B절 `user_reviewed` ·
        #173 값별 경계표). 새 초안이 되는 다른 후보 선택만 되돌린다(`reselect_candidate()`).
        `case_rev`도 따로 올리지 않는다 — 같은 요청의 결과다(재선택과 같다)."""
        if self.stage == "READY":
            self.stage = "EVIDENCE_REVIEW"

    def next_job_id(self, kind: str) -> str:
        """case가 발주하는 모든 JobRecord는 **항상 새 job_id**를 받는다.
        같은 job_id + attempt 증가는 자동 인프라 재시도(STALE)뿐이고, 그건 case가 아니라
        common/runtime이 하는 일이다(module-architecture.md §4-모듈5 ④) — 그래서 case
        코드에는 "기존 job_id 재사용" 분기가 아예 존재하지 않는다."""
        return f"job_{self.case_id}_{kind.lower()}_{uuid.uuid4().hex[:8]}"

    def record_job(self, job_record: dict[str, Any]) -> None:
        self.job_records.append(job_record)

    def settle_job(self, job_id: str, reason: str) -> bool:
        """case가 `job_id`의 결과를 더 기다리지 않는다고 기록한다. 이미 정산된 job이면 처음 사유를
        유지하고 `False` — 같은 결과가 두 번 와도 같다(#245 D-5). `case_rev`는 올리지 않는다."""
        if reason not in JOB_SETTLE_REASONS:
            raise ValueError(f"알 수 없는 정산 사유: {reason!r} (등록된 사유: {JOB_SETTLE_REASONS})")
        if not any(r["job_id"] == job_id for r in self.job_records):
            raise ValueError(f"이 case가 발주하지 않은 job_id: {job_id!r}")
        if job_id in self.settled_jobs:
            return False
        self.settled_jobs[job_id] = reason
        return True

    def waiting_job_records(self) -> list[dict[str, Any]]:
        """아직 정산되지 않은 JobRecord — `running_jobs[]`의 원천. `job_records` 순서."""
        return [r for r in self.job_records if r["job_id"] not in self.settled_jobs]

    def _reflect_waiting(self, kind: str) -> None:
        for record in self.waiting_job_records():
            if record["kind"] == kind:
                self.settle_job(record["job_id"], "REFLECTED")
