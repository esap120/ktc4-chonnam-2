"""Mock Fixture 기반 upstream adapter — recording/search/readout/evidence가 아직 코드가
없는 상태에서 case를 독립적으로 실행·테스트하기 위한 stand-in이다.

`data/mock/<module>/scenario_<id>.json`을 Canonical Contract 모양 그대로 읽어서 돌려준다.
여기서 하는 일은 오직 "파일을 읽어서 그대로 넘기는 것"뿐 — evidence의 판정 로직이나
readout의 OCR 판단을 이 어댑터가 재구현하지 않는다(그건 각 모듈 Owner의 책임).

나중에 실제 모듈이 구현되면, 이 클래스와 같은 메서드 시그니처를 갖는 실제 HTTP/함수
호출 어댑터로 교체하면 된다 — case의 domain/view 코드는 이 인터페이스에만 의존한다.

## Mock→Real 교체 (W5)

`ModuleAdapter`가 그 "인터페이스"를 `typing.Protocol`로 formalize한 것이다.
`MockFixtureAdapter`와 `RealAdapter` 둘 다 구조적으로 이 프로토콜을 만족한다(명시적
상속 없이도 각 메서드 시그니처가 같으면 타입체커가 호환으로 본다). `case/service.py`는
구체 클래스가 아니라 `ModuleAdapter`에만 의존하므로, 실행 시점에 어느 어댑터 인스턴스를
주입하느냐만 바꾸면 orchestration 코드는 손대지 않는다.

`RealAdapter`는 모듈별로 하나씩 채워진다 — 나머지는 계속 `NotImplementedError`로 남겨서
"이 모듈은 이미 Real, 저 모듈은 아직 Mock"인 혼재 상태를 그대로 표현한다(W5 원칙
"Mock retained for not-yet-ready modules").

## 2026-09-18 갱신 — search만 real로 교체됨

`search.search_candidates()`/`evidence.*`/common의 실제 코드 존재 여부를 다시 확인한
결과:

- **search**: `search_candidates(scope)`가 순수하게 `AnalysisScope` 하나만 받아 완결된
  결과를 주므로 real로 교체했다(`get_candidate_events()`).
- **evidence**: 함수 자체(`assemble_evidence` 등)는 이미 완성돼 있지만, 그 입력으로
  요구하는 `plate_readout`(readout)·`incident_clip`(recording)을 case가 아직 못 구한다
  — `ModuleAdapter`에 readout/recording 메서드 자체가 없다. evidence Owner를 더 기다리는
  게 아니라 **case가 readout/recording까지 엮는 별도 설계**가 먼저 필요하다(오늘 범위 밖).
- **common/runtime**: `InMemoryJobExecutionStore`는 호출 가능한 서비스가 아니라 Worker
  프로세스가 채우는 저장소다. `worker/`가 아직 비어 있어 실제로 채워질 대상 자체가 없다.

## 2026-09-18(W6) 갱신 — evidence도 `scenario_happy_001` 대표 시나리오로 real 교체

W5/W6 마감(월요일 20:00 회의 — 대표 시나리오 1개가 E2E를 실제로 통과하는지 확인)에
맞춰 readout/recording도 이미 실제 공개 함수가 있다는 걸 확인했다(`real_e2e.py` 참고
— recording의 `resolve_span`/`build_incident_clip`, readout의 `read_plate`/
`read_overlay_time` 전부 fixture 없이도 순수 호출 가능). evidence 6개 메서드를
`real_e2e.build_happy_001_evidence_bundle()`로 교체했다 — recording→search.verify_visual
→readout→evidence 전체 체인을 실제 함수로 잇는다.

`get_job_executions()`(common/runtime)는 여전히 `NotImplementedError`다 — 다만
`case/service.py`의 `fetch_case_view_inputs()`/`build_view_from_adapter()`는 애초에
이 메서드를 부르지 않으므로(`running_jobs`는 case가 정산 기록으로 계산함), 오늘 목표인
"CaseView까지 E2E 통과"에는 영향이 없다.

시나리오는 `scenario_happy_001` 하나로 고정돼 있다 — `real_e2e.py` 모듈 docstring의
"알려진 단순화"(시각 원시 데이터 raw read, `situation_response`/`observation_facts`
None) 두 가지도 그대로 적용된다.

## 2026-09-19 갱신 — evidence가 case의 실제 선택값을 쓰도록 수정

`RealAdapter._build_evidence_bundle()`이 candidate/selection_rev를 `case` 상태에서
읽지 않고 `search.search_candidates()`를 다시 불러 `candidates[0]`을 쓰던 지점을
고쳤다 — evidence 파트가 W6 real E2E 체인을 검증하다 발견해 알려준 것(2026-09-19).
`RealAdapter`는 이제 `case`(`CaseAggregate`) 참조를 받아 `case.candidates`의
`selected=True` candidate와 `case.selection_rev`를 그대로 쓴다. `happy_001`은 후보가
하나뿐이라 지금까지 결과값 자체는 안 바뀌었지만, 배선이 case 상태를 실제로 따라가게
됐다는 점이 다르다.

## 2026-09-19 갱신(이슈 #73) — correction 적용 후 evidence 재계산이 실제로 일어나게 수정

Tool Trajectory 1차 Review WARN ①: 부분 재실행 정책 표가 `EVENT_TIME_MANUAL` 등은
"제자리, 요건 검사만 재발주"라고 정하고 있는데, 실제 배선에는 두 공백이 있었다.
`correction_records` 전달과 `case_rev` 기준 캐시 무효화를 추가해 정정 후 evidence가
실제로 다시 계산되게 한다. 별도 `JobRecord`는 발주하지 않는다.

## 2026-09-28 갱신(이슈 #73) — 정정 후에는 조립만 다시 한다

위 수정은 캐시가 무효화되면 evidence 묶음 전체를 처음부터 다시 만들어, Job 발주 없이
함수 호출로 search·Fine·readout이 다시 돌았다(`RealVideoAdapter`는 유료 Fine까지).
`real_e2e`를 관찰 단계(`observe_*`: Fine·IncidentClip·OCR·시간 source·AssetFacts)와 조립 단계
(`assemble_evidence_bundle()`: 시각·evidence·요건·Package)로 나눠, 선택 context
(`candidate_id`, `selection_rev`)가 같으면 관찰 결과를 재사용하고 조립만 다시 부른다. 새로
선택되면(`OTHER_CANDIDATE`, `TIME_HINT_EDIT` 후 재검색 — 같은 candidate_id가 다시 선택돼도)
관찰부터 다시 한다. `PLATE_REREAD`는 CorrectionRecord가 아니라
`EvidenceNeeds` → `jobs.issue_plate_reread()` Job 경로이고, `SPAN_ADJUST`는 candidate span을
바꾸는 배선이 아직 없어 두 경우 모두 이 캐시와 무관하다(수정 전에도 마찬가지).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from daesingo import search as search_module
from daesingo.case import real_e2e
from daesingo.case.domain import CaseAggregate


@runtime_checkable
class ModuleAdapter(Protocol):
    """`case`가 upstream 모듈 산출물을 읽을 때 의존하는 유일한 인터페이스.

    `MockFixtureAdapter`(현재)와 `RealAdapter`(골격, 앞으로 모듈별로 채워짐) 둘 다
    이 프로토콜을 만족한다. `case/service.py`의 함수들은 이 타입에만 의존한다 —
    Mock↔Real 교체는 여기 정의된 메서드 시그니처를 벗어나지 않는 한 `service.py`나
    `domain.py`/`jobs.py`/`view.py`를 고치지 않고도 가능하다.
    """

    def get_candidate_events(self) -> list[dict[str, Any]]: ...

    def get_candidate_search_outcome(self) -> str | None:
        """마지막 `CANDIDATE_SEARCH` Run의 `outcome`(SUCCEEDED·PARTIAL·FAILED). 없으면 None."""
        ...

    def get_analysis_scopes(self) -> list[dict[str, Any]]: ...

    def get_evidence_record(self) -> dict[str, Any] | None: ...

    def get_evidence_records(self) -> list[dict[str, Any]]: ...

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None: ...

    def get_requirement_reports(self, scope: str) -> list[dict[str, Any]]: ...

    def get_evidence_needs(self) -> list[dict[str, Any]]: ...

    def get_report_package(self) -> dict[str, Any] | None: ...

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        """선택된 후보의 `PlateReadout` 목록(원판독·재판독). `evidence.plate_preview_ref`(#47)가
        현재 값의 근거 판독을 `readout_id`로 찾는 데 쓴다."""
        ...

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        """`OverlayTimeReadout` 목록(원판독·재판독). 시각을 얻지 못한 갈래의 notice(`readout.overlay_*`,
        readout `failure-taxonomy.md`)가 현재 선택 후보의 가장 나중 판독을 근거로 쓴다."""
        ...

    def get_plate_read_status(self) -> str | None:
        """번호판 판독 실행 상태(`JobExecution.status` 값 공간). 보고할 실행 상태가 없으면 None."""
        ...

    def get_visual_evidence_decision(self) -> str | None:
        """선택된 후보 Fine 결과의 소비 판정(`VisualEvidenceDisposition.decision` 값 공간 —
        `ASSEMBLE`·`AWAIT_SITUATION_RESPONSE`·`NOT_ASSEMBLED`). 판정이 아직 없으면 None.
        음성 결과(`NOT_ASSEMBLED`)는 evidence가 없어 CaseView 값만으로 조립 전과 구분되지 않는다(#168 [A])."""
        ...

    def get_independent_facts(self) -> dict[str, Any] | None:
        """상황 응답 대기(`AWAIT_SITUATION_RESPONSE`) 중 evidence `resolve_independent_facts()`가 만든 상황
        독립 값(`occurred_at` · `vehicle_number` · `location`). CaseView `evidence` 부분 투영(`record_id=null`,
        #239)의 원천이다. EvidenceRecord가 아니며, 응답 대기가 아니면 None."""
        ...

    def get_job_executions(self) -> list[dict[str, Any]]: ...


class MockFixtureAdapter:
    def __init__(self, mock_root: Path, scenario_id: str) -> None:
        self.mock_root = Path(mock_root)
        self.scenario_id = scenario_id
        self._cache: dict[str, dict[str, Any]] = {}

    def _load(self, module: str) -> dict[str, Any]:
        if module not in self._cache:
            path = self.mock_root / module / f"scenario_{self.scenario_id}.json"
            with open(path, encoding="utf-8") as fh:
                self._cache[module] = json.load(fh)
        return self._cache[module]

    # ── search ──────────────────────────────────────────────────────────
    def get_candidate_events(self) -> list[dict[str, Any]]:
        """`AnalysisRun.operation == CANDIDATE_SEARCH`가 만든 `CandidateEvent`만 반환한다
        (`VISUAL_VERIFY`/Fine run은 후보를 만들지 않는다 — module-architecture.md §4-모듈2)."""
        search = self._load("search")
        candidates: list[dict[str, Any]] = []
        for entry in search.get("analysis_run_candidate_events", []):
            if entry["analysis_run"]["operation"] == "CANDIDATE_SEARCH":
                candidates.extend(entry.get("candidates", []))
        return candidates

    def get_candidate_search_outcome(self) -> str | None:
        runs = [
            entry["analysis_run"]
            for entry in self._load("search").get("analysis_run_candidate_events", [])
            if entry["analysis_run"]["operation"] == "CANDIDATE_SEARCH"
        ]
        return runs[-1]["outcome"] if runs else None

    def get_analysis_scopes(self) -> list[dict[str, Any]]:
        """search fixture에 실려있는 `AnalysisScope`(case가 Producer로 만들어 보낸 것)를
        그대로 읽는다 — `scope.build_analysis_scope()`의 정답지로 쓴다."""
        return self._load("search").get("analysis_scopes", [])

    def get_hints(self) -> dict[str, Any]:
        """대표 시나리오의 사용자 단서(`core-user-flow.md` §6 4칸)를 case 자신의 mock
        fixture(`case_views[0].hints`)에서 읽는다 — `intake()` 호출자가 실제 값을 채울 수
        있게 하려는 용도다(이슈 #103: real E2E 경로가 `hints={}`로 고정돼 후보 화면의
        「기억 단서와 대조」가 빈 채로 나왔다)."""
        case_views = self._load("case").get("case_views", [])
        return case_views[0].get("hints", {}) if case_views else {}

    # ── evidence ────────────────────────────────────────────────────────
    def get_evidence_record(self) -> dict[str, Any] | None:
        """현재(= supersede 체인의 마지막) `EvidenceRecord`. fixture는 v1→v2 순서로 적혀 있다.
        2026-09-28 정정: 예전엔 최초 1건(`records[0]`)을 돌려줘, 체인이 있는 시나리오를
        `service.build_view_from_adapter()`로 조립하면 옛 기록으로 CaseView가 만들어졌다
        (공용 H가 응답 전 v1 → CONFIRMED v2 체인이 되면서 드러남, #48 I1)."""
        records = self._load("evidence").get("evidence_records", [])
        return records[-1] if records else None

    def get_evidence_records(self) -> list[dict[str, Any]]:
        """`get_evidence_record()`는 현재 1건만 돌려준다 — supersede 체인(재판독 등으로
        `EvidenceRecord`가 v1→v2로 갱신되는 시나리오, `scenario_plate_reread_001`)을
        순서대로 재현하려면 전체 목록이 필요해서 추가했다."""
        return self._load("evidence").get("evidence_records", [])

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        """같은 scope의 현재(마지막) 보고서 — `get_evidence_record()`와 같은 원칙."""
        reports = self._load("evidence").get("requirement_reports", [])
        return next((r for r in reversed(reports) if r["scope"] == scope), None)

    def get_requirement_reports(self, scope: str) -> list[dict[str, Any]]:
        """`get_requirement_report()`와 같은 이유로 추가 — 같은 scope에 여러 건(supersede
        전/후)이 있는 시나리오를 순서대로 재현하려고 전체 목록을 돌려준다."""
        reports = self._load("evidence").get("requirement_reports", [])
        return [r for r in reports if r["scope"] == scope]

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        """`EvidenceRecord`와 마찬가지로 supersede 체인 순서대로(v1 basis→v2 basis) 전체
        목록을 돌려준다 — 각 `EvidenceNeeds.basis_record_ref`가 어느 `EvidenceRecord`
        revision을 기준으로 계산됐는지는 evidence의 책임이고, 이 어댑터는 그대로 옮기기만
        한다(`scenario_plate_reread_001`: v1 basis에 `PLATE_REREAD` 1건, v2 basis는 `items=[]`)."""
        return self._load("evidence").get("evidence_needs", [])

    def get_report_package(self) -> dict[str, Any] | None:
        packages = self._load("evidence").get("report_packages", [])
        return packages[-1] if packages else None

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        return self._load("readout").get("plate_readouts", [])

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        return self._load("readout").get("overlay_time_readouts", [])

    def get_plate_read_status(self) -> str | None:
        """mock fixture에는 이 case의 실행 상태 원장이 없다 — 시나리오 테스트가
        `plate_read_status`를 JobExecution fixture에서 직접 넘긴다(`scenario_infra_failure_001`)."""
        return None

    def get_visual_evidence_decision(self) -> str | None:
        """공용 mock fixture에는 음성(`NOT_OBSERVED`) 시나리오가 없다 — 판정을 보고하지 않는다."""
        return None

    def get_independent_facts(self) -> dict[str, Any] | None:
        """공용 mock fixture에는 상황 응답 대기 시나리오가 없다."""
        return None

    # ── common/runtime ──────────────────────────────────────────────────
    def get_job_executions(self) -> list[dict[str, Any]]:
        """`JobExecution`(job-execution/v1.1) 전체 목록 — case는 이 계약의 Producer가
        아니지만(common/runtime 소유), `progress[].state` projection(§13)의 입력으로
        읽어야 한다. `scenario_infra_failure_001`처럼 같은 `job_id`에 여러 attempt
        (STALE→FAILED)가 있을 수 있어 전체 목록을 그대로 돌려준다 — "어느 attempt가
        최신인가"를 고르는 건 이 어댑터가 아니라 호출자(case) 책임이다."""
        return self._load("common").get("job_executions", [])


class RealAdapter:
    """`ModuleAdapter`의 실제 구현 — 모듈별로 준비되는 대로 하나씩 채운다.

    search는 이미 채워졌다(`get_candidate_events()`). 나머지는 여전히
    `NotImplementedError`다 — 이 상태에서도 `case/service.py`는 그대로 동작해야 한다:
    실패는 "아직 Real로 안 바뀐 자리를 호출했다"는 명확한 신호여야 하고, 조용히 빈 값을
    돌려주면 안 된다(Mock의 정직한 실패 원칙과 동일).

    생성자 인자는 모듈별로 다르다 — search는 순수 함수 호출이라 `search_scope`(dict 또는
    `search.AnalysisScope`) 하나면 충분하고, evidence 체인은 추가로 `mock_root`가
    필요하다(`real_e2e.py`의 "알려진 단순화 1" — recording의 raw time_source_candidates
    읽기용, 나머지는 전부 real 함수 호출). evidence 체인은 이제 `case`(`CaseAggregate`)도
    필요하다 — case가 실제로 선택한 candidate/selection_rev를 읽어야 하기 때문이다
    (2026-09-19 수정, 아래 `_build_evidence_bundle()` 참고). 나머지가 채워질 때 필요한
    인자가 더 늘어난다.
    """

    def __init__(
        self,
        *,
        case_id: str,
        case: CaseAggregate | None = None,
        search_scope: dict[str, Any] | search_module.AnalysisScope | None = None,
        mock_root: Path | None = None,
        **clients: Any,
    ) -> None:
        self.case_id = case_id
        self._case = case
        self._search_scope = search_scope
        self._mock_root = mock_root
        self._evidence_bundle: real_e2e.EvidenceBundle | None = None
        self._evidence_bundle_case_rev: int | None = None
        # 관찰 단계 결과(Fine·IncidentClip·OCR)는 같은 탐색 결과(`case.candidate_generation`) 안에서
        # 후보별로 재사용한다 — 정정(이슈 #73)과 A→B→A 재선택(`decisions/reselect-observation-reuse.md`).
        # 세대가 바뀌면(재탐색) 같은 candidate_id라도 버린다(정책 표 1행).
        self._observations_by_candidate: dict[str, real_e2e.ObservationBundle] = {}
        self._observations_generation: int | None = None
        # 마지막 `get_candidate_events()`의 CandidateEvent — evidence 조립이 선택된 것을 여기서 찾는다.
        self._candidates_by_id: dict[str, search_module.CandidateEvent] = {}
        self._clients = clients

    def bind_case(self, case: CaseAggregate) -> None:
        """요청마다 방금 로드한 aggregate를 붙인다(`store.AdapterRegistry`). 캐시는 객체 동일성이 아니라
        `case_rev` · `candidate_generation` 값으로 판단하므로 그대로 동작한다."""
        self._case = case

    def _not_ready(self, method: str, module: str, *, reason: str) -> None:
        raise NotImplementedError(
            f"RealAdapter.{method}()는 아직 미구현 — {reason} "
            f"그 전까지는 이 case_id에 대해 {module}을 Mock으로 유지해야 한다."
        )

    # ── search ──────────────────────────────────────────────────────────
    def get_candidate_events(self) -> list[dict[str, Any]]:
        """`search.search_candidates(scope)`를 실제로 호출한다. `AnalysisRun.outcome ==
        FAILED`면 candidates가 빈 튜플이라는 게 `CandidateSearchResult`의 계약 불변조건
        이므로(`search/runs.py`), 여기서 outcome을 따로 분기하지 않고 그대로 반환한다."""
        if self._search_scope is None:
            self._not_ready(
                "get_candidate_events",
                "search",
                reason="생성자에 search_scope가 주어지지 않았다 — 호출자가 "
                "case.scope.build_analysis_scope()로 만든 값을 넘겨야 한다.",
            )
        scope = self._search_scope
        if not isinstance(scope, search_module.AnalysisScope):
            scope = search_module.AnalysisScope.model_validate(scope)
        result = search_module.search_candidates(scope)
        self._last_search_outcome = str(result.analysis_run.outcome)
        # evidence 조립이 선택된 CandidateEvent를 여기서 찾는다 — 조립 때 search를 다시 부르지
        # 않는다(정책 표 2행: 선택이 바뀌어도 1차 탐색은 안 건드림, `RealVideoAdapter`와 같은 원칙).
        self._candidates_by_id = {c.candidate_id: c for c in result.candidates}
        return [
            {
                "candidate_id": c.candidate_id,
                "summary": c.summary,
                "thumbnail_ref": c.thumbnail_ref,
                "rank": c.rank,
                "span": c.span.model_dump(mode="json"),
            }
            for c in result.candidates
        ]

    def get_candidate_search_outcome(self) -> str | None:
        return getattr(self, "_last_search_outcome", None)

    def get_analysis_scopes(self) -> list[dict[str, Any]]:
        """실제 대응이 없다 — case가 `AnalysisScope`의 Producer라(§`scope.py`), 다른
        모듈에서 "가져오는" 값이 아니다. Mock 쪽에서만 `test_scope.py`의 정답지 용도로
        쓰이므로 `RealAdapter`에는 채울 자리가 없다. 이 메서드를 부르는 real 경로가
        생기면 그 자체가 설계 오류 신호다."""
        self._not_ready(
            "get_analysis_scopes",
            "search",
            reason="이 메서드는 애초에 real 대응이 없다(case가 Producer) — 부르지 않아야 한다.",
        )

    # ── evidence ────────────────────────────────────────────────────────
    def _cached_observations(self, candidate_id: str) -> real_e2e.ObservationBundle | None:
        """같은 탐색 결과 세대 안에서 이미 관찰한 후보면 그 관찰을 준다. 세대가 바뀌었으면 전부 버린다."""
        generation = self._case.candidate_generation
        if self._observations_generation != generation:
            self._observations_by_candidate = {}
            self._observations_generation = generation
        return self._observations_by_candidate.get(candidate_id)

    def _build_evidence_bundle(self) -> real_e2e.EvidenceBundle:
        """evidence로 넘기는 candidate/selection_rev는 **case가 실제로 선택한 값**이어야
        한다(2026-09-19 수정) — 이전엔 이 메서드가 `search.search_candidates()`를 다시
        불러 `candidates[0]`을 그냥 썼다. `happy_001`은 후보가 하나뿐이라 우연히 값이
        같았을 뿐이고, `case.select_candidate()`가 고른 candidate와 무관하게 항상 같은
        결과가 나왔다 — 후보가 여럿인 시나리오에서는 case가 고른 것과 evidence가 받는
        것이 어긋날 수 있는 실제 버그였다. 지금은 `self._case.candidates`에서
        `selected=True`인 candidate를 찾아 그 `candidate_id`로 `get_candidate_events()`가 받아 둔
        `CandidateEvent`를 골라 넘기고(search를 다시 부르지 않는다 — W7 7순위 러너), `selection_rev`도 `self._case.selection_rev`를
        그대로 쓴다.

        correction이 적용돼 `case_rev`가 바뀌면 최신 `case.correction_records`로 evidence를
        다시 계산한다(이슈 #73). 이때 다시 부르는 것은 `assemble_evidence_bundle()`(시각·
        evidence·요건·Package)뿐이다 — 선택 context(`candidate_id`, `selection_rev`)가 그대로면
        search·Fine·readout을 다시 돌리지 않고 관찰 결과를 재사용한다(부분 재실행 정책 표:
        `EVENT_TIME_MANUAL` 등 "요건 검사만 다시"). 처음 보는 후보를 고르거나 재탐색으로 후보 목록이
        바뀌면 관찰부터 다시 한다 — 같은 탐색 결과에서 이미 본 후보로 돌아오면(A→B→A) 관찰은 재사용하고
        조립만 새 선택 context로 한다(`decisions/reselect-observation-reuse.md`)."""
        if self._evidence_bundle is None or self._evidence_bundle_case_rev != self._case.case_rev:
            if self._search_scope is None or self._mock_root is None:
                self._not_ready(
                    "get_evidence_record",
                    "evidence",
                    reason="evidence 체인에는 search_scope와 mock_root(recording의 raw "
                    "time_source_candidates 읽기용, real_e2e.py 「알려진 단순화 1」)가 "
                    "모두 필요하다.",
                )
            if self._case is None:
                self._not_ready(
                    "get_evidence_record",
                    "evidence",
                    reason="case가 실제로 선택한 candidate/selection_rev를 읽으려면 "
                    "생성자에 CaseAggregate가 필요하다 — case_id 문자열만으로는 어떤 "
                    "candidate가 선택됐는지 알 수 없다.",
                )
            selected = next((c for c in self._case.candidates if c.selected), None)
            if selected is None:
                self._not_ready(
                    "get_evidence_record",
                    "evidence",
                    reason=f"case_id={self.case_id!r}에 선택된(selected=True) candidate가 "
                    "없다 — case.select_candidate()가 evidence 조회보다 먼저 호출돼야 한다.",
                )
            scope = self._search_scope
            if not isinstance(scope, search_module.AnalysisScope):
                scope = search_module.AnalysisScope.model_validate(scope)
            observations = self._cached_observations(selected.candidate_id)
            if observations is None:
                candidate = self._candidates_by_id.get(selected.candidate_id)
                if candidate is None:
                    raise ValueError(
                        f"case가 선택한 candidate_id={selected.candidate_id!r}를 "
                        "get_candidate_events() 결과에서 찾을 수 없다 — 같은 인스턴스로 "
                        "먼저 후보를 받아왔는지 확인해야 한다."
                    )
                observations = real_e2e.observe_happy_001_candidate(
                    case_id=self.case_id,
                    candidate=candidate,
                    scope=scope,
                    mock_root=self._mock_root,
                )
                self._observations_by_candidate[selected.candidate_id] = observations
            self._evidence_bundle = real_e2e.assemble_evidence_bundle(
                observations,
                case_id=self.case_id,
                selection_rev=self._case.selection_rev,
                correction_records=self._case.correction_records,
                location_hint=self._case.hints.get("location"),
                situation_response=self._case.situation_response,
            )
            self._evidence_bundle_case_rev = self._case.case_rev
        return self._evidence_bundle

    def get_evidence_record(self) -> dict[str, Any] | None:
        return self._build_evidence_bundle().evidence_record

    def get_evidence_records(self) -> list[dict[str, Any]]:
        """`scenario_happy_001` 대표 시나리오는 supersede 체인이 없어(1건뿐) 리스트도
        1건이다 — plate_reread류 다건 체인은 W7 확장 대상(모듈 docstring 참고).

        Fine이 후보를 기각해(`NOT_OBSERVED`) 조립 자체가 없으면 빈 리스트다 — 그건
        조용한 실패가 아니라 `EvidenceBundle.disposition`에 사유가 남는 정상 결과다
        (이슈 #137)."""
        record = self._build_evidence_bundle().evidence_record
        return [record] if record is not None else []

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        bundle = self._build_evidence_bundle()
        if scope == "EVIDENCE":
            return bundle.requirement_report_evidence
        if scope == "FINAL_PACKAGE":
            return bundle.requirement_report_package
        raise ValueError(f"알 수 없는 requirement scope: {scope!r}")

    def get_requirement_reports(self, scope: str) -> list[dict[str, Any]]:
        report = self.get_requirement_report(scope)
        return [report] if report is not None else []

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        needs = self._build_evidence_bundle().evidence_needs
        return [needs] if needs is not None else []

    def get_report_package(self) -> dict[str, Any] | None:
        """`build_report_package()`가 `PackageNotReady`를 던지면(situation_response/
        observation_facts 미확보 — real_e2e.py 「알려진 단순화 2」) `None`을 돌려준다.
        이건 조용한 실패가 아니다 — `EvidenceBundle.package_error`에 사유가 남는다."""
        return self._build_evidence_bundle().report_package

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        plate_readout = self._build_evidence_bundle().plate_readout
        return [plate_readout] if plate_readout else []

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        overlay_readout = self._build_evidence_bundle().overlay_readout
        return [overlay_readout] if overlay_readout else []

    def get_plate_read_status(self) -> str | None:
        """동기 real 경로에는 JobExecution이 없어, 판독 호출 결과 `ReadoutRun.outcome=FAILED`를
        실행 실패로 보고한다(#172 [D] — 실행 실패를 「읽지 못함」과 가른다). 성공·부분 성공은
        evidence 조립 여부로 진행 상태가 정해지므로 보고하지 않는다."""
        return "FAILED" if self._build_evidence_bundle().plate_read_outcome == "FAILED" else None

    def get_visual_evidence_decision(self) -> str | None:
        return self._build_evidence_bundle().disposition.decision

    def get_independent_facts(self) -> dict[str, Any] | None:
        return self._build_evidence_bundle().independent_facts

    # ── common/runtime ──────────────────────────────────────────────────
    def get_job_executions(self) -> list[dict[str, Any]]:
        self._not_ready(
            "get_job_executions",
            "common/runtime",
            reason="InMemoryJobExecutionStore는 호출 가능한 서비스가 아니라 Worker "
            "프로세스가 채우는 저장소다 — worker/가 아직 비어 있어 채워질 대상이 없다.",
        )


class RealVideoAdapter:
    """`ModuleAdapter`의 real 영상(`register_local_source`) 구현.

    `RealAdapter`(fixture/`happy_001`)와 같은 `case/service.py` 흐름
    (`receive_search_candidates()` → `case.select_candidate()` →
    `build_view_from_adapter()`)을 그대로 쓰지만, 백엔드가 실제 로컬 영상이라
    생성자 인자가 다르다 — `real_e2e.RealVideoContext`(register_local_source
    ~real Gemini/Elice service 조립)를 한 번만 만들어 재사용한다
    (`prepare_real_video_context()`/`get_real_video_candidates()`/
    `build_evidence_for_real_video_candidate()`, 2026-09-22).

    `close()`를 호출자가 다 쓴 뒤 불러야 한다 — 안 그러면 `RecordingService`가
    등록한 로컬 원본이 메모리에 계속 남는다.
    """

    def __init__(
        self,
        *,
        case_id: str,
        case: CaseAggregate,
        local_video_path: Path | str,
        scope_id: str,
        target_event_types: list[str] | None = None,
    ) -> None:
        self.case_id = case_id
        self._case = case
        self._local_video_path = local_video_path
        self._scope_id = scope_id
        self._target_event_types = target_event_types
        self._context: real_e2e.RealVideoContext | None = None
        self._candidates_by_id: dict[str, search_module.CandidateEvent] = {}
        self._evidence_bundle: real_e2e.EvidenceBundle | None = None
        self._evidence_bundle_case_rev: int | None = None
        # 관찰 단계 결과(Fine·IncidentClip·OCR)는 같은 탐색 결과(`case.candidate_generation`) 안에서
        # 후보별로 재사용한다 — 정정(이슈 #73)과 A→B→A 재선택(`decisions/reselect-observation-reuse.md`).
        # 세대가 바뀌면(재탐색) 같은 candidate_id라도 버린다(정책 표 1행).
        self._observations_by_candidate: dict[str, real_e2e.ObservationBundle] = {}
        self._observations_generation: int | None = None

    def bind_case(self, case: CaseAggregate) -> None:
        """요청마다 방금 로드한 aggregate를 붙인다(`store.AdapterRegistry`). 캐시는 객체 동일성이 아니라
        `case_rev` · `candidate_generation` 값으로 판단하므로 그대로 동작한다."""
        self._case = case

    def _not_ready(self, method: str, module: str, *, reason: str) -> None:
        raise NotImplementedError(
            f"RealVideoAdapter.{method}()는 아직 미구현 — {reason} "
            f"그 전까지는 이 case_id에 대해 {module}을 Mock으로 유지해야 한다."
        )

    def _ensure_context(self) -> real_e2e.RealVideoContext:
        if self._context is None:
            self._context = real_e2e.prepare_real_video_context(
                local_video_path=self._local_video_path,
                case=self._case,
                scope_id=self._scope_id,
                target_event_types=self._target_event_types,
            )
        return self._context

    def close(self) -> None:
        """호출자가 evidence 조립까지 끝난 뒤 불러야 한다(모듈 docstring 참고) —
        search의 `open_analysis_source()` 소비가 끝나기 전에 부르면 안 된다."""
        if self._context is not None:
            self._context.rec_service.close()

    # ── search ──────────────────────────────────────────────────────────
    def get_candidate_events(self) -> list[dict[str, Any]]:
        """real Gemini/Elice **Coarse**를 실제로 호출한다(유료) — candidate 객체를
        `candidate_id`로 캐시해서 `get_evidence_record()`가 나중에 case가 실제
        선택한 것과 같은 객체를 다시 찾아 쓰게 한다(`RealAdapter`와 동일 원칙,
        2026-09-19 수정 참고)."""
        context = self._ensure_context()
        result = real_e2e.run_real_video_candidate_search(context)
        self._last_search_outcome = str(result.analysis_run.outcome)
        candidates = result.candidates
        self._candidates_by_id = {c.candidate_id: c for c in candidates}
        return [
            {
                "candidate_id": c.candidate_id,
                "summary": c.summary,
                "thumbnail_ref": c.thumbnail_ref,
                "rank": c.rank,
                "span": c.span.model_dump(mode="json"),
            }
            for c in candidates
        ]

    def get_candidate_search_outcome(self) -> str | None:
        return getattr(self, "_last_search_outcome", None)

    def get_analysis_scopes(self) -> list[dict[str, Any]]:
        self._not_ready(
            "get_analysis_scopes",
            "search",
            reason="이 메서드는 애초에 real 대응이 없다(case가 Producer) — 부르지 않아야 한다.",
        )

    # ── evidence ────────────────────────────────────────────────────────
    def _cached_observations(self, candidate_id: str) -> real_e2e.ObservationBundle | None:
        """같은 탐색 결과 세대 안에서 이미 관찰한 후보면 그 관찰을 준다. 세대가 바뀌었으면 전부 버린다."""
        generation = self._case.candidate_generation
        if self._observations_generation != generation:
            self._observations_by_candidate = {}
            self._observations_generation = generation
        return self._observations_by_candidate.get(candidate_id)

    def _build_evidence_bundle(self) -> real_e2e.EvidenceBundle:
        """`RealAdapter._build_evidence_bundle()`과 같은 원칙 — case가 실제로
        선택한 candidate로만 계산하고, case_rev가 바뀌면(정정 등) 조립만 다시 한다.
        real Gemini/Elice **Fine**은 같은 탐색 결과에서 처음 보는 후보일 때만 실제로 호출한다(유료) — 정정은
        관찰 결과를 재사용한다(이슈 #73)."""
        if self._evidence_bundle is None or self._evidence_bundle_case_rev != self._case.case_rev:
            selected = next((c for c in self._case.candidates if c.selected), None)
            if selected is None:
                self._not_ready(
                    "get_evidence_record",
                    "evidence",
                    reason=f"case_id={self.case_id!r}에 선택된(selected=True) candidate가 "
                    "없다 — case.select_candidate()가 evidence 조회보다 먼저 호출돼야 한다.",
                )
            candidate = self._candidates_by_id.get(selected.candidate_id)
            if candidate is None:
                raise ValueError(
                    f"case가 선택한 candidate_id={selected.candidate_id!r}를 "
                    "get_candidate_events() 결과에서 찾을 수 없다 — 같은 인스턴스로 "
                    "먼저 후보를 받아왔는지 확인해야 한다."
                )
            observations = self._cached_observations(selected.candidate_id)
            if observations is None:
                context = self._ensure_context()
                observations = real_e2e.observe_real_video_candidate(
                    context, candidate, case_id=self.case_id
                )
                self._observations_by_candidate[selected.candidate_id] = observations
            self._evidence_bundle = real_e2e.assemble_evidence_bundle(
                observations,
                case_id=self.case_id,
                selection_rev=self._case.selection_rev,
                correction_records=self._case.correction_records,
                location_hint=self._case.hints.get("location"),
                situation_response=self._case.situation_response,
            )
            self._evidence_bundle_case_rev = self._case.case_rev
        return self._evidence_bundle

    def get_evidence_record(self) -> dict[str, Any] | None:
        return self._build_evidence_bundle().evidence_record

    def get_evidence_records(self) -> list[dict[str, Any]]:
        """Fine이 후보를 기각해(`NOT_OBSERVED`) 조립 자체가 없으면 빈 리스트다 — 그건
        조용한 실패가 아니라 `EvidenceBundle.disposition`에 사유가 남는 정상 결과다
        (이슈 #137, `RealAdapter.get_evidence_records()`와 동일 패턴)."""
        record = self._build_evidence_bundle().evidence_record
        return [record] if record is not None else []

    def get_requirement_report(self, scope: str) -> dict[str, Any] | None:
        bundle = self._build_evidence_bundle()
        if scope == "EVIDENCE":
            return bundle.requirement_report_evidence
        if scope == "FINAL_PACKAGE":
            return bundle.requirement_report_package
        raise ValueError(f"알 수 없는 requirement scope: {scope!r}")

    def get_requirement_reports(self, scope: str) -> list[dict[str, Any]]:
        report = self.get_requirement_report(scope)
        return [report] if report is not None else []

    def get_evidence_needs(self) -> list[dict[str, Any]]:
        needs = self._build_evidence_bundle().evidence_needs
        return [needs] if needs is not None else []

    def get_report_package(self) -> dict[str, Any] | None:
        return self._build_evidence_bundle().report_package

    def get_plate_readouts(self) -> list[dict[str, Any]]:
        plate_readout = self._build_evidence_bundle().plate_readout
        return [plate_readout] if plate_readout else []

    def get_overlay_time_readouts(self) -> list[dict[str, Any]]:
        overlay_readout = self._build_evidence_bundle().overlay_readout
        return [overlay_readout] if overlay_readout else []

    def get_plate_read_status(self) -> str | None:
        """동기 real 경로에는 JobExecution이 없어, 판독 호출 결과 `ReadoutRun.outcome=FAILED`를
        실행 실패로 보고한다(#172 [D] — 실행 실패를 「읽지 못함」과 가른다). 성공·부분 성공은
        evidence 조립 여부로 진행 상태가 정해지므로 보고하지 않는다."""
        return "FAILED" if self._build_evidence_bundle().plate_read_outcome == "FAILED" else None

    def get_visual_evidence_decision(self) -> str | None:
        return self._build_evidence_bundle().disposition.decision

    def get_independent_facts(self) -> dict[str, Any] | None:
        return self._build_evidence_bundle().independent_facts

    # ── common/runtime ──────────────────────────────────────────────────
    def get_job_executions(self) -> list[dict[str, Any]]:
        self._not_ready(
            "get_job_executions",
            "common/runtime",
            reason="InMemoryJobExecutionStore는 호출 가능한 서비스가 아니라 Worker "
            "프로세스가 채우는 저장소다 — worker/가 아직 비어 있어 채워질 대상이 없다.",
        )
