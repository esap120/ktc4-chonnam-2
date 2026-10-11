# 분석 시작(START_ANALYSIS, 8-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 「분석 시작」을 누르면 case가 단서 구조화(`HINT_EXTRACT`)를 발주하고, 그 결과가 반영되면 `AnalysisScope` 1건과 `COARSE_SEARCH` 1건을 발주하는 경로를 만든다. 영상 개수와 무관하게 같은 경로로 동작한다.

**Architecture:** 등록 때 원본마다 `{source_asset_ref, video_stream_ref, duration_sec}`를 aggregate에 남긴다. 타임라인은 port `CaseTimelineSource`로 받고, 임시 구현 `RecordingSequentialTimelineSource`가 recording 공개 함수로 원본을 등록 순서대로 이어 붙인다. case 로직(`analysis_start.py`)은 타임라인 하나로 범위 하나를 만들고, command(`START_ANALYSIS`)와 Worker 반영 진입 함수(`service.receive_hint_extraction_result`)가 그 로직을 부른다.

**Tech Stack:** Python 3.12 · pytest · 기존 `daesingo.recording.RecordingService`

**Spec:** `docs/modules/case/decisions/start-analysis.md` (case-command Draft §11 · `decisions/running-jobs-derivation.md` · `decisions/command-appended-job-records.md`도 함께 읽는다)

## Global Constraints

- 브랜치 `feat/case-start-analysis`(#282 · #284 · #286을 합친 상태)에서 작업한다. 브랜치를 바꾸거나 push하지 않는다.
- `target_event_types`는 항상 `["SIGNAL", "CENTER_LINE_CROSSING", "SOLID_LINE_LANE_CHANGE", "MOTORCYCLE_HELMET_NON_USE"]`(이 순서).
- 예산 기본값: `max_cost_krw = 1000.0`, `max_latency_sec = 150.0`.
- 시간 구간: `[{"kind": "TIMELINE_RELATIVE", "timeline_ref": {"timeline_id": …, "revision": …}, "start_ms": 0, "end_ms": duration_ms}]` 1개.
- fingerprint: `"sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()`.
  - `HINT_EXTRACT` payload: `{"kind": "HINT_EXTRACT", "description": <원문>, "prior_hints": None}`
  - `COARSE_SEARCH` payload: `{"kind": "COARSE_SEARCH", "scope": <scope dict에서 "scope_id" 키를 뺀 것>}`
- `scope_id` = `"scope_" + uuid.uuid4().hex`.
- 설명 원문은 받은 그대로 `case.description`에 저장한다. 비었는지는 `description.strip() == ""`로 판단한다.
- `START_ANALYSIS`는 `case_rev`를 올리지 않는다(`case.start_search()`가 이미 그렇다). 단서 반영도 올리지 않는다.
- 저장소는 commit하지 않는다. 실패한 command · 반영은 `store.save()`를 부르지 않는다.
- 다른 모듈(`src/daesingo/recording` · `search` 등) 코드는 고치지 않는다.
- 테스트 실행 전 PATH에 static_ffmpeg bin을 앞에 붙인다: `export PATH="$(python -c 'import static_ffmpeg,os;print(os.path.join(os.path.dirname(static_ffmpeg.__file__),"bin","win32"))'):$PATH"`.
- 커밋 메시지는 한국어 `feat(case): … (8-1)` 모양, 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 한 줄만.
- 기존 코드 스타일(한국어 docstring · 주석)을 따른다.

## Review Focus

1. **같은 단서 구조화 결과가 두 번 도착** — 두 번째는 아무것도 바꾸지 않고(`COARSE_SEARCH` 중복 발주 없음) 빈 목록을 돌려줘야 한다. → Task 3 · Task 4 테스트.
2. **타임라인을 만들지 못함(VIDEO 스트림이 둘인 파일이 섞임 등)** — command · 반영 모두 예외가 올라가고 저장되지 않아야 한다(다음 load에 흔적 없음). → Task 4 테스트.
3. **공백만 적은 설명** — 원문 그대로 저장하고 구조화 없이 바로 `COARSE_SEARCH`. → Task 3 테스트.
4. **분석 시작을 두 번 누름** — 두 번째는 `not_allowed`, 상태 무변화. → Task 4 테스트.
5. **영상 없이(또는 처리 불가 영상만) 분석 시작** — `not_allowed`. → Task 4 테스트.

---

## File Structure

- Modify `src/daesingo/case/domain.py` — `description` · `sources` 필드, `record_source_registered(source_asset, media_streams=None)`.
- Modify `src/daesingo/case/store_state.py` — 두 필드 저장.
- Modify `src/daesingo/case/view.py` — `"description": case.description`.
- Modify `src/daesingo/case/service.py` — `record_source_registered(..., media_streams=None)` 전달, `receive_hint_extraction()` 위임, `ReflectionResult` · `receive_hint_extraction_result()`.
- Create `src/daesingo/case/timeline_source.py` — `CaseTimeline` · `CaseTimelineSource` · `TimelineUnavailable` · `RecordingSequentialTimelineSource`.
- Create `src/daesingo/case/analysis_start.py` — 예산 · fingerprint · `start_analysis` · `issue_initial_search` · `hints_from_result` · `reflect_hint_extraction`.
- Modify `src/daesingo/case/command.py` — `START_ANALYSIS`, `timelines=` · `budget=` 주입.
- Modify `docs/modules/case/contracts/contract-case-command.md` · `docs/modules/case/design-refinement-w7-baseline.md` (Task 5).
- Tests: `tests/case/test_case_sources.py` · `tests/case/test_timeline_source.py` · `tests/case/test_analysis_start.py` · `tests/case/test_start_analysis_command.py`(신규), `tests/case/test_view_description.py`(수정).

---

### Task 1: 원본 · 설명 상태 (domain · store_state · view · service 등록)

**Files:**
- Modify: `src/daesingo/case/domain.py`
- Modify: `src/daesingo/case/store_state.py:19-28`
- Modify: `src/daesingo/case/view.py` (`"description": None,` 줄)
- Modify: `src/daesingo/case/service.py:460-469`
- Test: `tests/case/test_case_sources.py`, `tests/case/test_view_description.py`

**Interfaces:**
- Produces: `CaseAggregate.description: str | None`(기본 `None`), `CaseAggregate.sources: list[dict]`(기본 `[]`, 원소 `{"source_asset_ref": str, "video_stream_ref": str | None, "duration_sec": float | None}`), `CaseAggregate.record_source_registered(source_asset: dict, media_streams: list[dict] | None = None) -> None`, `service.record_source_registered(case_id, source_asset, *, media_streams=None, store)`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_case_sources.py`

```python
"""등록된 원본 기록 — 분석 시작이 타임라인을 만들 입력(`decisions/start-analysis.md` §3-1)."""

from daesingo.case import service
from daesingo.case.domain import CaseAggregate
from daesingo.case.store import CaseStore


def _asset(ref: str, *, availability: str = "AVAILABLE", duration: float | None = 10.0) -> dict:
    return {"source_asset_ref": ref, "availability": availability, "duration_sec": duration}


def _streams(*types: str) -> list[dict]:
    return [{"media_stream_ref": f"ms_{i}", "media_type": t} for i, t in enumerate(types)]


def test_available_source_is_recorded_with_unique_video_stream():
    case = CaseAggregate.empty("case_src1")
    case.record_source_registered(_asset("sa_1"), _streams("VIDEO", "AUDIO"))
    assert case.sources == [{"source_asset_ref": "sa_1", "video_stream_ref": "ms_0", "duration_sec": 10.0}]


def test_two_video_streams_record_no_stream_ref():
    case = CaseAggregate.empty("case_src2")
    case.record_source_registered(_asset("sa_1"), _streams("VIDEO", "VIDEO"))
    assert case.sources[0]["video_stream_ref"] is None


def test_without_streams_argument_records_no_stream_ref():
    case = CaseAggregate.empty("case_src3")
    case.record_source_registered(_asset("sa_1"))
    assert case.sources == [{"source_asset_ref": "sa_1", "video_stream_ref": None, "duration_sec": 10.0}]


def test_unavailable_source_is_counted_but_not_recorded():
    case = CaseAggregate.empty("case_src4")
    case.record_source_registered(_asset("sa_1", availability="UNAVAILABLE"), _streams("VIDEO"))
    assert case.manifest_summary["file_count"] == 1
    assert case.sources == []


def test_sources_keep_registration_order():
    case = CaseAggregate.empty("case_src5")
    case.record_source_registered(_asset("sa_b"), _streams("VIDEO"))
    case.record_source_registered(_asset("sa_a"), _streams("VIDEO"))
    assert [s["source_asset_ref"] for s in case.sources] == ["sa_b", "sa_a"]


def test_sources_and_description_survive_store_round_trip():
    store = CaseStore()
    case_id = service.create_case(store=store)
    service.record_source_registered(case_id, _asset("sa_1"), media_streams=_streams("VIDEO"), store=store)
    case = store.load_for_update(case_id)
    case.description = "흰 SUV"
    store.save(case)
    loaded = store.get_case(case_id)
    assert loaded.sources[0]["video_stream_ref"] == "ms_0"
    assert loaded.description == "흰 SUV"
```

`tests/case/test_view_description.py`의 `test_description_is_null_before_analysis_start` 아래에 추가:

```python
def test_description_is_projected_from_case():
    case = CaseAggregate.intake(case_id="case_desc2", hints={}, manifest_summary={})
    case.description = "  "
    assert build_case_view(case)["description"] == "  "
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_case_sources.py tests/case/test_view_description.py -q` → `TypeError`(인자 개수) · `AttributeError: sources` 등으로 FAIL.

- [ ] **Step 3: 구현**

`domain.py` — `settled_jobs` 필드 아래(또는 `analysis_scopes` 아래, `extra_state` 위)에:

```python
    # 분석 시작 때 사용자가 적은 설명 원문(case-command Draft §11). 받은 그대로 두고 CaseView `description`으로
    # 내린다. 분석 시작 전에는 `None`.
    description: str | None = None

    # 처리 가능한 등록 원본(등록 순서) — `{source_asset_ref, video_stream_ref, duration_sec}`. 분석 시작이 타임라인을
    # 만들 입력이다(`decisions/start-analysis.md` §3-1). `video_stream_ref`는 등록 때 VIDEO가 정확히 하나였을 때만
    # 있다 — case가 여러 VIDEO 중 하나를 고르지 않는다. CaseView 비노출.
    sources: list[dict[str, Any]] = field(default_factory=list)
```

`record_source_registered()`를 다음으로 바꾼다(docstring 첫 단락은 유지하고 마지막에 한 문장 추가):

```python
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
```

`store_state.py` `_STATE_FIELDS` 끝에 `"description",` `"sources",` 두 줄 추가.

`view.py`의 `"description": None,`과 그 위 두 줄 주석을 다음으로 바꾼다:

```python
        # 분석 시작 때 사용자가 적은 설명 원문(v1.7, #259) — 받은 그대로. 분석 시작 전에는 `null`.
        "description": case.description,
```

`service.py` `record_source_registered`:

```python
def record_source_registered(
    case_id: str,
    source_asset: dict[str, Any],
    *,
    media_streams: list[dict[str, Any]] | None = None,
    store: CaseStore,
) -> None:
```

docstring 끝에 「`media_streams`(`MediaStream` 계약 dict 목록, recording 등록 결과)를 넘기면 VIDEO 스트림 ref를 함께 남긴다 — 분석 시작이 여러 원본을 이어 붙일 때 쓴다」를 더하고, 본문 `case.record_source_registered(source_asset)` → `case.record_source_registered(source_asset, media_streams)`.

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case -q`. 기존 `test_empty_case.py` 포함 모두 통과해야 한다(그 파일의 `_source_asset()` 헬퍼는 이미 `source_asset_ref`를 넣는다).

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case/domain.py src/daesingo/case/store_state.py src/daesingo/case/view.py src/daesingo/case/service.py tests/case/test_case_sources.py tests/case/test_view_description.py
git commit -m "feat(case): 등록 원본 · 설명 원문을 aggregate에 남김 — 분석 시작 입력 (8-1)"
```

---

### Task 2: 타임라인 port와 임시 구현

**Files:**
- Create: `src/daesingo/case/timeline_source.py`
- Test: `tests/case/test_timeline_source.py`

**Interfaces:**
- Consumes: Task 1의 `sources` 원소 모양.
- Produces: `CaseTimeline(timeline_id: str, revision: int, duration_ms: int)`(frozen dataclass), `CaseTimelineSource` Protocol(`timeline_for(sources: list[dict]) -> CaseTimeline`), `TimelineUnavailable(RuntimeError)`, `RecordingSequentialTimelineSource(recording: RecordingService)`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_timeline_source.py`

```python
"""타임라인 port 임시 구현 — 등록 순서대로 이어 붙인다(`decisions/start-analysis.md` §3-1)."""

import hashlib

import pytest

from daesingo.case.timeline_source import CaseTimeline, RecordingSequentialTimelineSource, TimelineUnavailable
from daesingo.recording import RecordingService
from daesingo.recording.probe import LocalSource, ProbedStream


def _service(video_streams: int = 1, duration: float = 10.0) -> RecordingService:
    class Probe:
        def probe(self, path):
            stat = path.stat()
            streams = tuple(ProbedStream(i, "VIDEO", duration) for i in range(video_streams))
            streams += (ProbedStream(video_streams, "AUDIO", None),)
            return LocalSource(path, stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest(),
                               duration, streams)

    return RecordingService(media_probe=Probe())


def _register(service: RecordingService, tmp_path, name: str) -> dict:
    path = tmp_path / name
    path.write_bytes(name.encode())
    registered = service.register_local_source(path)
    videos = [s.media_stream_ref for s in registered.media_streams if s.media_type == "VIDEO"]
    return {
        "source_asset_ref": registered.source_asset.source_asset_ref,
        "video_stream_ref": videos[0] if len(videos) == 1 else None,
        "duration_sec": registered.source_asset.duration_sec,
    }


def test_single_source_uses_relative_timeline(tmp_path):
    service = _service()
    source = _register(service, tmp_path, "a.mp4")
    timeline = RecordingSequentialTimelineSource(service).timeline_for([source])
    assert isinstance(timeline, CaseTimeline)
    assert timeline.revision == 1
    assert timeline.duration_ms == 10_000
    placements = service.get_timeline(timeline.timeline_id, timeline.revision).source_placements
    assert [p.source_asset_ref for p in placements] == [source["source_asset_ref"]]


def test_two_sources_are_placed_back_to_back_in_registration_order(tmp_path):
    service = _service()
    first = _register(service, tmp_path, "b.mp4")
    second = _register(service, tmp_path, "a.mp4")
    timeline = RecordingSequentialTimelineSource(service).timeline_for([first, second])
    assert timeline.duration_ms == 20_000
    placements = service.get_timeline(timeline.timeline_id, timeline.revision).source_placements
    assert [(p.source_asset_ref, p.timeline_start_sec, p.timeline_end_sec) for p in placements] == [
        (first["source_asset_ref"], 0.0, 10.0),
        (second["source_asset_ref"], 10.0, 20.0),
    ]


def test_no_sources_is_unavailable():
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(_service()).timeline_for([])


def test_multiple_sources_need_a_video_stream_each(tmp_path):
    service = _service(video_streams=2)
    sources = [_register(service, tmp_path, "a.avi"), _register(service, tmp_path, "b.avi")]
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(service).timeline_for(sources)


def test_multiple_sources_need_known_duration(tmp_path):
    service = _service()
    sources = [_register(service, tmp_path, "a.mp4"), _register(service, tmp_path, "b.mp4")]
    sources[1] = dict(sources[1], duration_sec=None)
    with pytest.raises(TimelineUnavailable):
        RecordingSequentialTimelineSource(service).timeline_for(sources)
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_timeline_source.py -q` → `ModuleNotFoundError: daesingo.case.timeline_source`.

- [ ] **Step 3: 구현** — `src/daesingo/case/timeline_source.py`

```python
"""분석 범위가 가리킬 case 타임라인 — 교체 가능한 port(`decisions/start-analysis.md` §3-1).

case당 RecordingTimeline 하나로 범위 하나를 만든다. 여러 원본을 하나로 정렬하는 일은 recording 책임이고
(`module-architecture.md` §4 recording ②), 그 기능이 생기기 전까지 `RecordingSequentialTimelineSource`가 기존
recording 공개 함수로 **등록 순서대로 이어 붙인다** — 이 순서 판단은 임시이며 이 클래스 안에만 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TimelineUnavailable(RuntimeError):
    """타임라인을 만들 수 없다 — 원본 없음 · VIDEO 스트림을 정할 수 없음 · 길이를 모름."""


@dataclass(frozen=True)
class CaseTimeline:
    timeline_id: str
    revision: int
    duration_ms: int


class CaseTimelineSource(Protocol):
    def timeline_for(self, sources: list[dict[str, Any]]) -> CaseTimeline: ...


def _case_timeline(timeline: Any) -> CaseTimeline:
    end_sec = max(p.timeline_end_sec for p in timeline.source_placements)
    return CaseTimeline(timeline_id=timeline.timeline_id, revision=timeline.revision, duration_ms=round(end_sec * 1000))


class RecordingSequentialTimelineSource:
    """임시 구현 — 원본 1개는 `create_relative_timeline()`, 여러 개는 등록 순서대로 앞 원본 끝에 이어 붙인다.

    전방 · 후방을 별도 파일로 찍은 경우 앞뒤로 놓이는 한계가 있다(spec §3-1 한계 1). recording이 case
    타임라인 정렬을 맡게 되면 이 구현만 바꾼다."""

    def __init__(self, recording: Any) -> None:
        self._recording = recording

    def timeline_for(self, sources: list[dict[str, Any]]) -> CaseTimeline:
        if not sources:
            raise TimelineUnavailable("처리 가능한 원본이 없다")
        if len(sources) == 1:
            return _case_timeline(self._recording.create_relative_timeline(sources[0]["source_asset_ref"]))
        placements = []
        start = 0.0
        for source in sources:
            if source.get("video_stream_ref") is None:
                raise TimelineUnavailable(f"VIDEO 스트림을 정할 수 없는 원본: {source['source_asset_ref']!r}")
            duration = source.get("duration_sec")
            if not duration or duration <= 0:
                raise TimelineUnavailable(f"길이를 모르는 원본: {source['source_asset_ref']!r}")
            placements.append(
                {
                    "source_asset_ref": source["source_asset_ref"],
                    "media_stream_ref": source["video_stream_ref"],
                    "timeline_start_sec": start,
                    "timeline_end_sec": start + float(duration),
                }
            )
            start += float(duration)
        return _case_timeline(self._recording.create_relative_timeline_from_placements(placements))
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case/test_timeline_source.py -q` → PASS. recording이 `ValueError`(placement 검증)를 던지는 경우는 그대로 올라간다 — 테스트는 그 경로를 다루지 않는다.

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case/timeline_source.py tests/case/test_timeline_source.py
git commit -m "feat(case): 분석 범위용 타임라인 port와 등록 순서 임시 구현 (8-1)"
```

---

### Task 3: 분석 시작 · 단서 반영 · 첫 탐색 발주 로직

**Files:**
- Create: `src/daesingo/case/analysis_start.py`
- Modify: `src/daesingo/case/service.py:71-93` (`_HINT_FIELDS` · `receive_hint_extraction`)
- Test: `tests/case/test_analysis_start.py`

**Interfaces:**
- Consumes: Task 1 `case.description` · `case.sources`; Task 2 `CaseTimeline` · `CaseTimelineSource`; 기존 `jobs.issue_job` · `jobs.issue_coarse_search(case, *, scope_ref, input_fingerprint, scope)` · `scope.build_analysis_scope(case, *, scope_id, time_ranges, target_event_types, max_cost_krw, max_latency_sec)` · `case.start_search()` · `case.record_extracted_hints(hints)` · `case.waiting_job_records()` · `case.settle_job(job_id, reason)`.
- Produces:
  - `TARGET_EVENT_TYPES: tuple[str, ...]`
  - `InitialSearchBudget(max_cost_krw: float = 1000.0, max_latency_sec: float = 150.0)` (frozen dataclass)
  - `AnalysisStartNotAllowed(Exception)`
  - `fingerprint(payload: dict) -> str`
  - `hints_from_result(result: dict) -> dict[str, str | None]`
  - `start_analysis(case, description: str, *, timelines: CaseTimelineSource, budget: InitialSearchBudget) -> None`
  - `issue_initial_search(case, *, timelines, budget) -> dict` (발주한 JobRecord)
  - `reflect_hint_extraction(case, result: dict, *, timelines, budget) -> bool` (반영했으면 True)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_analysis_start.py`

```python
"""분석 시작 로직 — `decisions/start-analysis.md` §2 · §3."""

import pytest

from daesingo.case import analysis_start as a
from daesingo.case.domain import CaseAggregate, InvalidTransition
from daesingo.case.timeline_source import CaseTimeline, TimelineUnavailable

BUDGET = a.InitialSearchBudget()


class FakeTimelines:
    def __init__(self, duration_ms: int = 20_000, fail: bool = False):
        self.calls: list[list[dict]] = []
        self.duration_ms = duration_ms
        self.fail = fail

    def timeline_for(self, sources):
        self.calls.append(sources)
        if self.fail:
            raise TimelineUnavailable("fake")
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=self.duration_ms)


def _case(n_sources: int = 1) -> CaseAggregate:
    case = CaseAggregate.empty("case_as")
    for i in range(n_sources):
        case.record_source_registered(
            {"source_asset_ref": f"sa_{i}", "availability": "AVAILABLE", "duration_sec": 10.0},
            [{"media_stream_ref": f"ms_{i}", "media_type": "VIDEO"}],
        )
    return case


def _ok(**hints):
    return {"status": "OK", **{f"{k}_hint": v for k, v in hints.items()}}


def test_description_issues_hint_extract_only():
    case, timelines = _case(), FakeTimelines()
    a.start_analysis(case, "흰 SUV가 끼어들었어요", timelines=timelines, budget=BUDGET)
    assert case.stage == "SEARCHING"
    assert case.case_rev == 1
    assert case.description == "흰 SUV가 끼어들었어요"
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT"]
    assert case.job_records[0]["input_fingerprint"] == a.fingerprint(
        {"kind": "HINT_EXTRACT", "description": "흰 SUV가 끼어들었어요", "prior_hints": None}
    )
    assert timelines.calls == []


@pytest.mark.parametrize("description", ["", "   "])
def test_blank_description_issues_coarse_search_directly(description):
    case = _case()
    a.start_analysis(case, description, timelines=FakeTimelines(), budget=BUDGET)
    assert case.description == description
    assert [r["kind"] for r in case.job_records] == ["COARSE_SEARCH"]
    assert case.hints == {"time": None, "vehicle": None, "situation": None, "location": None}


def test_no_processable_source_is_not_allowed():
    case = _case(n_sources=0)
    with pytest.raises(a.AnalysisStartNotAllowed):
        a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    assert case.stage == "INTAKE"
    assert case.description is None


def test_second_start_is_rejected_by_stage():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    with pytest.raises(InvalidTransition):
        a.start_analysis(case, "y", timelines=FakeTimelines(), budget=BUDGET)
    assert case.description == "x"


def test_initial_search_scope_shape():
    case = _case(n_sources=2)
    timelines = FakeTimelines(duration_ms=20_000)
    a.start_analysis(case, "", timelines=timelines, budget=BUDGET)
    job = case.job_records[-1]
    scope = case.analysis_scopes[job["scope_ref"]]
    assert timelines.calls == [case.sources]
    assert scope["time_ranges"] == [
        {"kind": "TIMELINE_RELATIVE", "timeline_ref": {"timeline_id": "tl_1", "revision": 1}, "start_ms": 0, "end_ms": 20_000}
    ]
    assert scope["target_event_types"] == list(a.TARGET_EVENT_TYPES)
    assert scope["budget"] == {"max_cost_krw": 1000.0, "max_latency_sec": 150.0}
    assert job["input_fingerprint"] == a.fingerprint(
        {"kind": "COARSE_SEARCH", "scope": {k: v for k, v in scope.items() if k != "scope_id"}}
    )


def test_fingerprint_ignores_scope_id():
    first, second = _case(), _case()
    a.start_analysis(first, "", timelines=FakeTimelines(), budget=BUDGET)
    a.start_analysis(second, "", timelines=FakeTimelines(), budget=BUDGET)
    assert first.job_records[0]["scope_ref"] != second.job_records[0]["scope_ref"]
    assert first.job_records[0]["input_fingerprint"] == second.job_records[0]["input_fingerprint"]


def test_reflect_ok_fills_hints_settles_and_issues_coarse():
    case = _case()
    a.start_analysis(case, "흰 SUV", timelines=FakeTimelines(), budget=BUDGET)
    hint_job = case.job_records[0]
    assert a.reflect_hint_extraction(case, _ok(vehicle="흰 SUV", time=" "), timelines=FakeTimelines(), budget=BUDGET)
    assert case.hints == {"time": None, "vehicle": "흰 SUV", "situation": None, "location": None}
    assert case.settled_jobs[hint_job["job_id"]] == "REFLECTED"
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]
    scope = case.analysis_scopes[case.job_records[-1]["scope_ref"]]
    assert scope["hint"]["vehicle"] == "흰 SUV"
    assert case.case_rev == 1


@pytest.mark.parametrize("status", ["ABSTAINED", "FAILED"])
def test_reflect_abstained_or_failed_uses_empty_hints(status):
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    assert a.reflect_hint_extraction(case, {"status": status, "vehicle_hint": "무시"}, timelines=FakeTimelines(), budget=BUDGET)
    assert case.hints == {"time": None, "vehicle": None, "situation": None, "location": None}
    assert [r["kind"] for r in case.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]


def test_duplicate_result_changes_nothing():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    a.reflect_hint_extraction(case, _ok(vehicle="v"), timelines=FakeTimelines(), budget=BUDGET)
    before = (dict(case.hints), len(case.job_records))
    assert a.reflect_hint_extraction(case, _ok(vehicle="다른 값"), timelines=FakeTimelines(), budget=BUDGET) is False
    assert (case.hints, len(case.job_records)) == before


def test_unknown_status_raises_before_any_change():
    case = _case()
    a.start_analysis(case, "x", timelines=FakeTimelines(), budget=BUDGET)
    with pytest.raises(ValueError):
        a.reflect_hint_extraction(case, {"status": "WHAT"}, timelines=FakeTimelines(), budget=BUDGET)
    assert case.settled_jobs == {}
    assert len(case.job_records) == 1


def test_timeline_failure_propagates():
    case = _case()
    with pytest.raises(TimelineUnavailable):
        a.start_analysis(case, "", timelines=FakeTimelines(fail=True), budget=BUDGET)
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_analysis_start.py -q` → `ModuleNotFoundError: daesingo.case.analysis_start`.

- [ ] **Step 3: 구현** — `src/daesingo/case/analysis_start.py`

```python
"""분석 시작 — 설명 원문 보존 · 단서 구조화 발주 · 결과 반영 · 첫 탐색 발주(`decisions/start-analysis.md`).

aggregate 수준 함수만 둔다. load · save와 append된 JobRecord 반환은 호출자(command · service)가 한다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from daesingo.case import jobs
from daesingo.case.domain import CaseAggregate, InvalidTransition
from daesingo.case.scope import build_analysis_scope
from daesingo.case.timeline_source import CaseTimelineSource

# 사용자가 유형을 고르는 입력이 없어 늘 4개 전부(spec §3-2).
TARGET_EVENT_TYPES: tuple[str, ...] = (
    "SIGNAL",
    "CENTER_LINE_CROSSING",
    "SOLID_LINE_LANE_CHANGE",
    "MOTORCYCLE_HELMET_NON_USE",
)

_HINT_FIELDS = {"time": "time_hint", "vehicle": "vehicle_hint", "situation": "situation_hint", "location": "location_hint"}


@dataclass(frozen=True)
class InitialSearchBudget:
    """첫 탐색 예산(spec §3-3). `max_cost_krw`는 설정값 — composition root가 바꿔 넘길 수 있다."""

    max_cost_krw: float = 1000.0
    max_latency_sec: float = 150.0


class AnalysisStartNotAllowed(Exception):
    """처리 가능한 원본이 없어 분석을 시작할 수 없다."""


def fingerprint(payload: dict[str, Any]) -> str:
    """첫 발주 `input_fingerprint`(spec §3-4) — 구현 이름표는 아직 섞지 않는다."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hints_from_result(result: dict[str, Any]) -> dict[str, str | None]:
    """search 단서 구조화 결과 → `hints` 4개 키. `OK`만 옮기고 빈 문자열은 `None`, `ABSTAINED` · `FAILED`는
    4개 모두 `None`(값을 지어내지 않는다). 그 밖의 상태는 결과 모양이 바뀐 것이라 `ValueError`."""
    status = result.get("status")
    if status == "OK":
        return {key: (result.get(field) or "").strip() or None for key, field in _HINT_FIELDS.items()}
    if status in ("ABSTAINED", "FAILED"):
        return dict.fromkeys(_HINT_FIELDS)
    raise ValueError(f"알 수 없는 단서 구조화 결과 상태: {status!r} (OK · ABSTAINED · FAILED)")


def issue_initial_search(
    case: CaseAggregate, *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> dict[str, Any]:
    """case 타임라인 전체로 범위 1개를 만들고 `COARSE_SEARCH` 1건을 발주한다. 타임라인 실패는 그대로 올린다."""
    timeline = timelines.timeline_for(case.sources)
    scope = build_analysis_scope(
        case,
        scope_id=f"scope_{uuid.uuid4().hex}",
        time_ranges=[
            {
                "kind": "TIMELINE_RELATIVE",
                "timeline_ref": {"timeline_id": timeline.timeline_id, "revision": timeline.revision},
                "start_ms": 0,
                "end_ms": timeline.duration_ms,
            }
        ],
        target_event_types=list(TARGET_EVENT_TYPES),
        max_cost_krw=budget.max_cost_krw,
        max_latency_sec=budget.max_latency_sec,
    )
    content = {k: v for k, v in scope.items() if k != "scope_id"}
    return jobs.issue_coarse_search(
        case,
        scope_ref=scope["scope_id"],
        input_fingerprint=fingerprint({"kind": "COARSE_SEARCH", "scope": content}),
        scope=scope,
    )


def start_analysis(
    case: CaseAggregate, description: str, *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> None:
    """`INTAKE`에서만(`start_search()`가 아니면 `InvalidTransition`), 처리 가능한 원본이 1개 이상일 때만 시작한다.
    설명이 비었으면(공백만 포함) 구조화 없이 바로 첫 탐색, 아니면 `HINT_EXTRACT`를 발주한다. 검사는 상태를
    바꾸기 전에 한다."""
    if case.stage != "INTAKE":
        raise InvalidTransition(f"{case.stage}에서는 분석을 시작할 수 없다(INTAKE 전용)")
    if not case.sources:
        raise AnalysisStartNotAllowed("처리 가능한 영상이 없다")
    case.description = description
    case.start_search()
    if not description.strip():
        # 타임라인 실패는 그대로 올라간다 — aggregate는 바뀐 채지만 호출자가 save하지 않는다(Task 4).
        issue_initial_search(case, timelines=timelines, budget=budget)
        return
    jobs.issue_job(
        case,
        "HINT_EXTRACT",
        input_fingerprint=fingerprint({"kind": "HINT_EXTRACT", "description": description, "prior_hints": None}),
    )


def reflect_hint_extraction(
    case: CaseAggregate, result: dict[str, Any], *, timelines: CaseTimelineSource, budget: InitialSearchBudget
) -> bool:
    """기다리던 `HINT_EXTRACT`가 있을 때만 hints를 채우고 정산한 뒤 첫 탐색을 발주한다. 없으면(같은 결과의
    두 번째 도착) 아무것도 바꾸지 않고 `False`. 결과 상태는 상태를 바꾸기 전에 검사한다."""
    waiting = [r for r in case.waiting_job_records() if r["kind"] == "HINT_EXTRACT"]
    if not waiting:
        return False
    hints = hints_from_result(result)
    case.record_extracted_hints(hints)
    for record in waiting:
        case.settle_job(record["job_id"], "REFLECTED")
    issue_initial_search(case, timelines=timelines, budget=budget)
    return True
```

**원자성:** 검사(stage · 원본)는 상태를 바꾸기 전에 한다. 빈 설명 경로에서 타임라인이 실패하면 aggregate는 `description` · stage가 바뀐 채 예외가 올라가지만, 호출자(command · service)는 예외가 나면 `save`하지 않으므로 저장소에는 남지 않는다 — Task 4 테스트가 이 계약을 지킨다.

`service.py` — `_HINT_FIELDS` 상수를 지우고 `receive_hint_extraction()` 본문을 위임으로 바꾼다(docstring은 유지하되 「매핑은 `analysis_start.hints_from_result()`」 한 줄을 더한다):

```python
from daesingo.case.analysis_start import hints_from_result  # 파일 상단 import 묶음에

def receive_hint_extraction(case: CaseAggregate, result: dict[str, Any]) -> None:
    ...  # docstring 유지
    case.record_extracted_hints(hints_from_result(result))
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case/test_analysis_start.py tests/case/test_hint_extraction.py -q` → PASS, 이어서 `python -m pytest tests/case -q`.

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case/analysis_start.py src/daesingo/case/service.py tests/case/test_analysis_start.py
git commit -m "feat(case): 분석 시작 · 단서 반영 · 첫 탐색 발주 로직 (8-1)"
```

---

### Task 4: command `START_ANALYSIS` · Worker 반영 진입 함수 · 시나리오 smoke

**Files:**
- Modify: `src/daesingo/case/command.py`
- Modify: `src/daesingo/case/service.py` (끝에 `ReflectionResult` · `receive_hint_extraction_result`)
- Test: `tests/case/test_start_analysis_command.py`

**Interfaces:**
- Consumes: Task 3 전부, Task 2 `RecordingSequentialTimelineSource`, Task 1 `service.record_source_registered(..., media_streams=)`.
- Produces: `execute_command(request, *, store, job_executions=None, notices=None, timelines=None, budget=None) -> CommandResult`, `handle_command(...)` 같은 키워드, `ReflectionResult(appended_job_records: list[dict], reflected: bool)`, `service.receive_hint_extraction_result(case_id: str, result: dict, *, store: CaseStore, timelines: CaseTimelineSource, budget: InitialSearchBudget | None = None) -> ReflectionResult`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/case/test_start_analysis_command.py`

```python
"""START_ANALYSIS command · Worker 반영 진입 함수 · 여러 영상 smoke(`decisions/start-analysis.md`)."""

import hashlib

import pytest

from daesingo.case import command, service
from daesingo.case.analysis_start import InitialSearchBudget
from daesingo.case.store import CaseStore
from daesingo.case.timeline_source import CaseTimeline, RecordingSequentialTimelineSource, TimelineUnavailable
from daesingo.recording import RecordingService
from daesingo.recording.probe import LocalSource, ProbedStream


class FakeTimelines:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def timeline_for(self, sources):
        if self.fail:
            raise TimelineUnavailable("fake")
        return CaseTimeline(timeline_id="tl_1", revision=1, duration_ms=10_000)


def _store_with_sources(n: int) -> tuple[CaseStore, str]:
    store = CaseStore()
    case_id = service.create_case(store=store)
    for i in range(n):
        service.record_source_registered(
            case_id,
            {"source_asset_ref": f"sa_{i}", "availability": "AVAILABLE", "duration_sec": 10.0},
            media_streams=[{"media_stream_ref": f"ms_{i}", "media_type": "VIDEO"}],
            store=store,
        )
    return store, case_id


def _start(case_id: str, description: str, rev: int = 1) -> dict:
    return {"case_id": case_id, "expected_case_rev": rev, "kind": "START_ANALYSIS", "payload": {"description": description}}


def test_start_returns_hint_extract_as_appended_and_pending():
    store, case_id = _store_with_sources(1)
    result = command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=FakeTimelines())
    assert result.response["ok"] is True
    assert [r["kind"] for r in result.appended_job_records] == ["HINT_EXTRACT"]
    view = result.response["case_view"]
    assert view["stage"] == "SEARCHING"
    assert view["description"] == "흰 SUV"
    assert [(j["kind"], j["status"]) for j in view["running_jobs"]] == [("HINT_EXTRACT", "PENDING")]


def test_blank_start_returns_coarse_search():
    store, case_id = _store_with_sources(1)
    result = command.execute_command(_start(case_id, ""), store=store, timelines=FakeTimelines())
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]


def test_start_without_sources_is_not_allowed_and_saves_nothing():
    store, case_id = _store_with_sources(0)
    result = command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.not_allowed"
    assert store.get_case(case_id).stage == "INTAKE"


def test_second_start_is_not_allowed():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    result = command.execute_command(_start(case_id, "y"), store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.not_allowed"
    assert result.appended_job_records == []
    assert store.get_case(case_id).description == "x"


def test_missing_description_key_is_invalid_payload():
    store, case_id = _store_with_sources(1)
    request = {"case_id": case_id, "expected_case_rev": 1, "kind": "START_ANALYSIS", "payload": {}}
    result = command.execute_command(request, store=store, timelines=FakeTimelines())
    assert result.response["error"]["code"] == "case.command.invalid_payload"


def test_timeline_failure_in_command_propagates_and_saves_nothing():
    store, case_id = _store_with_sources(1)
    with pytest.raises(TimelineUnavailable):
        command.execute_command(_start(case_id, ""), store=store, timelines=FakeTimelines(fail=True))
    saved = store.get_case(case_id)
    assert saved.stage == "INTAKE"
    assert saved.job_records == []


def test_start_without_injected_timelines_is_a_programming_error():
    store, case_id = _store_with_sources(1)
    with pytest.raises(RuntimeError):
        command.execute_command(_start(case_id, "x"), store=store)


def test_reflection_entrypoint_returns_appended_coarse_search():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=FakeTimelines())
    result = service.receive_hint_extraction_result(
        case_id, {"status": "OK", "vehicle_hint": "흰 SUV"}, store=store, timelines=FakeTimelines()
    )
    assert result.reflected is True
    assert [r["kind"] for r in result.appended_job_records] == ["COARSE_SEARCH"]
    saved = store.get_case(case_id)
    assert saved.hints["vehicle"] == "흰 SUV"
    assert [r["kind"] for r in saved.job_records] == ["HINT_EXTRACT", "COARSE_SEARCH"]


def test_duplicate_reflection_returns_nothing():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines())
    again = service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines())
    assert again.reflected is False
    assert again.appended_job_records == []
    assert len(store.get_case(case_id).job_records) == 2


def test_reflection_timeline_failure_saves_nothing():
    store, case_id = _store_with_sources(1)
    command.execute_command(_start(case_id, "x"), store=store, timelines=FakeTimelines())
    with pytest.raises(TimelineUnavailable):
        service.receive_hint_extraction_result(case_id, {"status": "OK"}, store=store, timelines=FakeTimelines(fail=True))
    saved = store.get_case(case_id)
    assert saved.settled_jobs == {}
    assert [r["kind"] for r in saved.job_records] == ["HINT_EXTRACT"]


def test_budget_is_injectable():
    store, case_id = _store_with_sources(1)
    command.execute_command(
        _start(case_id, ""), store=store, timelines=FakeTimelines(), budget=InitialSearchBudget(max_cost_krw=500.0)
    )
    saved = store.get_case(case_id)
    assert next(iter(saved.analysis_scopes.values()))["budget"]["max_cost_krw"] == 500.0


def test_two_videos_end_to_end_with_recording(tmp_path):
    """빈 case → 업로드 2개 → START_ANALYSIS → 반영 → COARSE_SEARCH(이어 붙인 20초 타임라인)."""

    class Probe:
        def probe(self, path):
            stat = path.stat()
            return LocalSource(path, stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest(),
                               10.0, (ProbedStream(0, "VIDEO", 10.0), ProbedStream(1, "AUDIO", None)))

    recording = RecordingService(media_probe=Probe())
    store = CaseStore()
    case_id = service.create_case(store=store)
    for name in ("a.mp4", "b.mp4"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        registered = recording.register_local_source(path)
        service.record_source_registered(
            case_id,
            registered.source_asset.model_dump(mode="json"),
            media_streams=[s.model_dump(mode="json") for s in registered.media_streams],
            store=store,
        )
    timelines = RecordingSequentialTimelineSource(recording)
    command.execute_command(_start(case_id, "흰 SUV"), store=store, timelines=timelines)
    result = service.receive_hint_extraction_result(case_id, {"status": "ABSTAINED"}, store=store, timelines=timelines)
    coarse = result.appended_job_records[0]
    scope = store.get_case(case_id).analysis_scopes[coarse["scope_ref"]]
    assert scope["time_ranges"][0]["end_ms"] == 20_000
    view = service.get_view(case_id, store=store)
    assert [j["kind"] for j in view["running_jobs"]] == ["COARSE_SEARCH"]
    recording.close()
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/case/test_start_analysis_command.py -q` → `invalid_payload` 단언 실패 · `TypeError: unexpected keyword 'timelines'` 등으로 FAIL.

- [ ] **Step 3: 구현**

`command.py`:
- import에 `from daesingo.case import analysis_start`와 `from daesingo.case.analysis_start import AnalysisStartNotAllowed, InitialSearchBudget`, `from daesingo.case.timeline_source import CaseTimelineSource` 추가.
- `_PAYLOAD_KEYS`에 `"START_ANALYSIS": frozenset({"description"}),` 추가.
- `_HANDLERS` 정의 위에 handler를 추가한다. handler 시그니처는 다른 handler와 같이 `(case, payload, view)`이고, 주입값은 `execute_command`가 `functools.partial`로 묶는다:

```python
def _start_analysis(
    case: CaseAggregate,
    payload: dict[str, Any],
    view: dict[str, Any],
    *,
    timelines: CaseTimelineSource | None,
    budget: InitialSearchBudget,
) -> None:
    # 타임라인 구현은 composition root가 주입한다 — 없이 부르는 것은 배선 오류다(사용자 거부가 아니다).
    if timelines is None:
        raise RuntimeError("START_ANALYSIS에는 timelines(CaseTimelineSource) 주입이 필요하다")
    try:
        analysis_start.start_analysis(case, payload["description"], timelines=timelines, budget=budget)
    except (InvalidTransition, AnalysisStartNotAllowed):
        raise _Rejected("not_allowed") from None
```

- `handle_command` · `execute_command` 시그니처에 `timelines: CaseTimelineSource | None = None, budget: InitialSearchBudget | None = None`를 추가하고 `handle_command`는 그대로 넘긴다. `execute_command` 안에서 handler 호출부를 다음으로 바꾼다:

```python
    handler = _HANDLERS[request["kind"]]
    if request["kind"] == "START_ANALYSIS":
        handler = functools.partial(_start_analysis, timelines=timelines, budget=budget or InitialSearchBudget())
    jobs_before = len(case.job_records)
    try:
        handler(case, request["payload"], view)
    except _Rejected as rejected:
        return CommandResult(_response(rejected.reason, view))
```

(`import functools` 추가, `_HANDLERS`에는 `"START_ANALYSIS": _start_analysis` 항목을 넣어 `kind` 목록이 한곳에 남게 한다. `_start_analysis`의 `timelines`가 키워드 전용이라 `_HANDLERS`에서 직접 부르는 경로는 없다.) `RuntimeError` · `TimelineUnavailable` · recording 예외는 잡지 않는다 — `save` 전에 올라가므로 저장되지 않는다. `execute_command` docstring에 「`START_ANALYSIS`는 `timelines`(필수) · `budget`(기본 `InitialSearchBudget()`)을 쓴다」 한 줄을 더한다.

`service.py` 끝에:

```python
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
```

`service.py` import 묶음에 `import copy`(없으면), `from dataclasses import dataclass`(이미 있으면 생략), `from daesingo.case.analysis_start import InitialSearchBudget, hints_from_result, reflect_hint_extraction`, `from daesingo.case.timeline_source import CaseTimelineSource`를 맞춰 넣는다. **순환 import 주의:** `analysis_start`는 `service`를 import하지 않는다(Task 3에서 그렇게 만들었다).

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/case -q`, 이어서 전체 `python -m pytest -q`. 오류 코드는 `_response()`가 `case.command.<사유>`로 만든다(테스트 기대값과 같다).

- [ ] **Step 5: 커밋**

```bash
git add src/daesingo/case/command.py src/daesingo/case/service.py tests/case/test_start_analysis_command.py
git commit -m "feat(case): START_ANALYSIS command · 단서 반영 진입 함수 (8-1)"
```

---

### Task 5: 계약 · 상태 문서

**Files:**
- Modify: `docs/modules/case/contracts/contract-case-command.md` (§2 표 · §11)
- Modify: `docs/modules/case/design-refinement-w7-baseline.md` (8-1 · 8-16 행)

- [ ] **Step 1: case-command 계약**
  - §2 「이 판본에 넣는 command」 표에 `START_ANALYSIS` 행을 추가한다: `kind` `START_ANALYSIS` · 화면 「영상에서 찾아보기」(홈) · 근거 「#247 H-2 · `decisions/start-analysis.md`」.
  - §11 머리말의 「상태: 제안 — 이 판본(v0)에 들어 있지 않고, 코드도 없다」를 「**상태: 구현(2026-10-07, 8-1) — 이 판본에 넣는다.** 결정은 `decisions/start-analysis.md`」로 바꾸고, 「미결이 닫히기 전에는 §2로 옮기지 않는다」 문장을 지운다.
  - §11 「미결」 목록을 「닫힌 미결」로 바꾸고 각 항목 끝에 닫은 곳을 단다: 1 → `case-view/v1.7`(#286), 2 · 3 · 4 → `decisions/start-analysis.md` §3-3 · §3-4 · §3-5, 5 → 「8-12 ✅ · #277 ✅ · Worker handler는 Runtime #297」.
  - §11 「`COARSE_SEARCH`는 1건이다」 항목 끝에 「영상이 여러 개여도 case 타임라인 하나로 1건이다(`decisions/start-analysis.md` §3-1)」를 더한다.
  - 같은 문서 다른 절의 「분석 시작 · 중단 — 다음 판본 후보」 줄(§2 아래)은 「분석 시작은 이 판본(§11), 중단은 다음 판본(#245 C-1a 뒤)」으로 고친다.

- [ ] **Step 2: 고도화 문서** — 8-1 행 맨 앞에 「🔄 **분석 시작 구현(2026-10-07) — `START_ANALYSIS` · 단서 반영 진입 함수 · 타임라인 port(임시: 등록 순서 이어 붙이기). 결정 `decisions/start-analysis.md`. 중단 command는 남음.**」, 8-16 행 맨 앞에 「✅ **2026-10-07 — 반영 함수 + `service.receive_hint_extraction_result()`(첫 탐색 발주까지). Worker 배선은 Runtime #297.**」을 붙인다.

- [ ] **Step 3: 확인** — `python -m pytest tests/case -q`(문서만이라 변화 없음), `git diff --stat`으로 두 문서만 바뀌었는지 본다.

- [ ] **Step 4: 커밋**

```bash
git add docs/modules/case/contracts/contract-case-command.md docs/modules/case/design-refinement-w7-baseline.md
git commit -m "docs(case): case-command 계약에 START_ANALYSIS 정식 등재 · 8-1 상태 갱신"
```
