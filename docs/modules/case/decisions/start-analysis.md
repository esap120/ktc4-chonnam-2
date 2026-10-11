# 분석 시작(`START_ANALYSIS`) — command · 단서 반영 · 첫 탐색 발주

> **상태: 결정 · 구현 전** · 결정일 2026-10-07 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-1(`../design-refinement-w7-baseline.md`), case-command Draft §11(`../contracts/contract-case-command.md`), #247 H-2 · H-3 · H-5, #210 · #277(search 단서 구조화 함수), #313(여러 영상 · 탐지 유형 의견 수렴)
> Draft §11이 이미 정한 것(빈 설명 · 실패 notice 없음 · `case_rev` 유지 · `HINT_EXTRACT` 이름 · CaseView `description`)은 다시 정하지 않는다. 이 문서는 Draft §11의 **미결 2 · 3 · 4**와 여러 영상 처리를 정하고, 구현 범위를 적는다. 규칙 원문은 구현 때 case-command 계약 정식 판본으로 옮긴다.

## 1. 목표 · 성공 기준

사용자가 「영상에서 찾아보기」를 누르면 탐색까지 자동으로 이어지는 **제품 진입 경로**를 case에 만든다.

- 영상이 올라간 case에 `START_ANALYSIS` → 202 응답(`running_jobs`에 `HINT_EXTRACT` 또는 `COARSE_SEARCH`, `PENDING`) → 단서 구조화 결과 반영 → `AnalysisScope` 1건 + `COARSE_SEARCH` 1건 발주까지 테스트로 이어진다.
- 영상 개수(1개 · 여러 개)와 무관하게 같은 경로로 동작한다.

**범위 밖:** Worker가 search 함수 · 탐색을 실제로 부르는 handler(Runtime #297) · 결과 반영의 `execution_id` idempotency(8-8) · 대기 timeout 동작 · 중단 command(8-9) · 클립 분할(#168) · 시간 단서로 범위 좁히기(§6).

## 2. 흐름

```
[API] START_ANALYSIS {description}
   ├─ 검사: stage=INTAKE · 처리 가능한 영상 ≥ 1 (아니면 not_allowed)
   ├─ 설명 원문 저장 · INTAKE→SEARCHING (case_rev 그대로)
   ├─ 설명이 비었으면(strip 후 "") → [첫 탐색 발주] 바로
   └─ 아니면 → HINT_EXTRACT 발주
   응답 202: case_view.running_jobs = [발주한 job, PENDING]  (8-7 · 8-11)

[Worker T2] 단서 구조화 결과 반영 — search IntentHintResult(OK · ABSTAINED · FAILED)
   load_for_update(case_id)
   ├─ hints: OK만 매핑, ABSTAINED · FAILED는 4개 모두 null (Draft §11)
   ├─ 기다리던 HINT_EXTRACT 정산(REFLECTED, decisions/running-jobs-derivation.md)
   └─ [첫 탐색 발주]
   save → 이번에 append한 JobRecord(COARSE_SEARCH)를 돌려줌 → composition root가 enqueue

[첫 탐색 발주] (공용)
   timeline = CaseTimelineSource.timeline_for(등록된 영상 ref 목록)
   scope    = 0 ~ timeline 길이 · 4개 유형 · hints · 예산
   scope 저장(record_analysis_scope) → COARSE_SEARCH 1건 발주(scope_ref · fingerprint)
```

## 3. 결정

### 3-1. 여러 영상 — case당 타임라인 하나, 교체 가능한 port로 받는다

- **case당 RecordingTimeline 하나**로 범위 1개 · `COARSE_SEARCH` 1건을 만든다. 아키텍처 결정 그대로다 — `module-architecture.md` §4 recording ② 「여러 파일을 하나의 RecordingTimeline으로 정렬한다」, recording ADR C안(case 하나에 논리 타임라인 하나 · `source_placements`), `core-user-flow.md` 「병합 방식은 recording이 관리한다」. Run이 하나라 여러 Run 후보 묶음 투영(#187 변경)이 필요 없다.
- case는 타임라인을 **port `CaseTimelineSource`** 하나로 받는다. case 로직은 영상 개수를 모른다.

  ```python
  class CaseTimelineSource(Protocol):
      def timeline_for(self, sources: list[dict]) -> CaseTimeline: ...
      # sources[i] = {"source_asset_ref", "video_stream_ref" | None, "duration_sec" | None} — 등록 순서

  @dataclass(frozen=True)
  class CaseTimeline:
      timeline_id: str
      revision: int
      duration_ms: int
  ```
- **임시 구현 `RecordingSequentialTimelineSource`** — recording의 기존 공개 함수만 쓴다.
  - 영상 1개: `create_relative_timeline(source_asset_ref)`.
  - 영상 2개 이상: `create_relative_timeline_from_placements()`로 **등록 순서대로 이어 붙인다**(각 원본을 앞 원본 끝에서 시작, gap 없음). 파일마다 VIDEO 스트림 하나는 지금 real 경로(`real_e2e.py` `_unique_video_media_stream_ref`)와 같이 **VIDEO 스트림이 정확히 하나인지 검증**해 쓴다 — 고르지 않는다(정철원 확인 2026-09-21 「유일성 검증이지 임의 선택이 아니다」).
  - **이 순서 판단은 원래 recording 책임이다.** case가 임시로 대신하며, 판단은 이 구현 안에만 둔다. recording이 정렬(파일명 시각 · 전후방 겹침 · gap)을 맡게 되면 이 구현 하나만 바꾼다. recording에 작업을 요청하지 않는다(#313 의견 수렴).
- **영상 스트림 ref는 등록할 때 받아 둔다.** recording 공개 경로에서 스트림 종류(VIDEO/AUDIO)를 알 수 있는 곳은 등록 결과(`register_local_source()` → `RegisteredSource.media_streams`)뿐이다. 그래서 `service.record_source_registered(case_id, source_asset, *, media_streams=None, store)`가 선택 인자로 스트림 목록을 받아, case가 VIDEO가 정확히 하나면 그 ref를, 아니면 `None`을 원본과 함께 저장한다(`sources`). 인자를 빼는 기존 호출은 그대로 동작한다(`video_stream_ref=None`).
- composition root가 구현을 주입한다. 테스트는 가짜 구현을 쓴다.

**알고 가는 한계**
1. 전방 · 후방을 **별도 파일**로 찍으면 앞뒤로 이어 붙여 후방 시각이 밀린다.
2. 이어 붙인 총 길이가 Coarse 한 번의 한도를 넘으면 실패할 수 있다 — 긴 영상 1개와 같은 기존 한계, 클립 분할(#168)로 풀린다.
3. 여러 파일 분석 입력은 recording(`prepare_analysis_source_from_resolution`)이 지원하지만 real 경로는 파일 1개로만 검증됐다.
4. **한 파일 안에 VIDEO 스트림이 둘 이상**(전방 · 후방이 한 AVI)이면 스트림을 고를 기준이 없어 실패한다 — 지금 real 경로와 같은 한계다. 기본 카메라 선택 정책은 recording이 정하지 않았다(`multi-source-timeline.md`). **영상이 1개여도 같다** — 임시 구현이 발주 전에 막는다(composition root는 등록 때 `media_streams`를 넘겨야 한다). 실패는 §3-7 「타임라인을 만들지 못함」과 같이 처리한다.
5. **부를 때마다 recording 타임라인이 새로 생긴다.** 같은 원본이어도 `timeline_id`가 달라져 `COARSE_SEARCH` fingerprint도 달라진다(재전달 · 재시도 때) — 재사용 캐시가 생기면 적중하지 않는다. recording 저장소가 case와 같은 transaction이 아니면 case rollback 뒤 타임라인이 고아로 남는다. recording의 case 타임라인 기능(또는 재사용 조회)이 생기면 함께 풀린다.

### 3-2. 탐지 대상 유형 — 항상 4개 전부

`target_event_types` = `SIGNAL` · `CENTER_LINE_CROSSING` · `SOLID_LINE_LANE_CHANGE` · `MOTORCYCLE_HELMET_NON_USE`. 사용자가 유형을 고르는 입력이 없고(web 첫 화면은 자유 문장 하나, 비워도 진행 — `apps/web/src/screens/UploadScreen.tsx`), 설명이 비어도 탐색이 돌아야 한다. 계약은 다중 유형을 허용한다(AnalysisScope 계약 ADR-003). 사용자 문장은 지금처럼 `hint`(`vehicle` · `free_text`)로만 넘긴다.

**위험:** search 실험은 클립마다 정답 유형 1개만 넣어 왔다(`event_types=(event,)`). 4개를 함께 넣은 성능은 미측정이다 — #313에서 search에 측정을 제안했다(선택).

### 3-3. 예산 — Draft §11 미결 2의 나머지

- `max_latency_sec` = **150초** — `timeout-fallback.md` 「Coarse 클립당 150초」.
- `max_cost_krw` = **설정값, 기본 1,000원** — 금액은 계약이 아니라 설정 관리 대상이다(`budget-krw-normalization.md`). 기본값은 지금 real 경로 값이다. 최근 search 실험의 Coarse 한 번이 약 5만 토큰(3.8 Flash 단가로 수십 원)이라 여유가 있다.
- 시간 구간 = 타임라인 전체 `TIMELINE_RELATIVE [0, duration_ms]` 1개.

### 3-4. 첫 발주의 `input_fingerprint` — Draft §11 미결 3

- 형식: `"sha256:" + sha256(키 정렬 · 공백 없는 JSON)`.
  - `HINT_EXTRACT`: `{"kind": "HINT_EXTRACT", "description": <원문>, "prior_hints": null}`
  - `COARSE_SEARCH`: `{"kind": "COARSE_SEARCH", "scope": <scope에서 scope_id를 뺀 것>}` — 같은 내용이면 같은 값.
- `decisions/input-fingerprint-implementation-label-deferred.md`가 미룬 것은 **구현 이름표를 섞는 부분**뿐이라 충돌하지 않는다. 재사용 캐시가 생기면 그때 이름표를 더한다.

### 3-5. 단서 구조화 대기 — Draft §11 미결 4

- case 대기 = **90초** — search 함수의 전체 상한 60초(재시도 포함, #277 `DEFAULT_INTENT_TIMEOUT_SEC`) + 큐 대기 여유 30초.
- 기다리다 멈추면 **빈 단서로 그대로 첫 탐색을 발주**한다(구조화 실패와 같은 처리, 사용자는 「전체 찾기」).
- 값과 동작만 정한다. 실제 대기 timeout은 8-9에서 구현한다.

### 3-6. 진입 함수 · 저장 경계

- **command:** `execute_command()`(8-6 · 8-7 그대로) — 성공 시 `CommandResult.appended_job_records`에 `HINT_EXTRACT` 또는 `COARSE_SEARCH`가 담긴다.
- **반영:** 새 `service.receive_hint_extraction_result(case_id, result, *, store, timelines, budget) -> ReflectionResult(appended_job_records)`. `load_for_update` → 반영 → **성공했을 때만** `save`, 이번에 append한 JobRecord를 돌려준다 — composition root(Worker T2)가 같은 transaction에서 enqueue한다(`CommandResult`와 같은 장치, `decisions/command-appended-job-records.md`). 저장소는 commit하지 않는다(#245 D-2).
- **정산 대상 · 중복 결과:** 아직 기다리는 `HINT_EXTRACT`(정산되지 않은 것)를 `REFLECTED`로 정산한다. **기다리는 `HINT_EXTRACT`가 없으면 아무것도 바꾸지 않는다** — 반영 뒤에도 stage는 `SEARCHING`(Coarse 대기)이라 stage 검사만으로는 같은 결과의 두 번째 도착을 막지 못하기 때문이다. execution 단위 idempotency는 8-8에서 한다.
- **설명 원문:** 받은 문자열을 **그대로** 저장해 CaseView `description`으로 내린다. 비었는지는 앞뒤 공백을 지운 뒤 판단한다(공백만 적으면 저장은 원문, 구조화는 생략).

### 3-7. 실패 처리

- **command:** 영상 0개 · `INTAKE` 아님(두 번째 클릭 포함) → `not_allowed`. payload 모양 → `invalid_payload`. 거부 시 상태를 바꾸지 않는다(case-command §6).
- **타임라인을 만들지 못함(recording 오류):** 예외를 그대로 올린다. command 단계면 요청 실패, Worker 반영 단계면 transaction rollback 후 Runtime 재전달에 맡긴다. 탐색 실패 notice로 바꾸지 않는다 — 그 notice의 「다시 찾기」는 이전 `COARSE_SEARCH`가 있어야 동작해, 사용자가 누를 버튼 없이 막힌다. **한계:** 계속 실패하면 `SEARCHING`에 머문다(8-9 timeout에서 다룬다).
- **반영 결과 모양이 모름(status 밖):** 지금처럼 `ValueError`로 멈춘다(`service.receive_hint_extraction()` 규칙 유지).

## 4. 구현 범위

| 위치 | 변경 |
| --- | --- |
| `domain.py` | aggregate에 `description: str \| None`, `sources: list[dict]`(처리 가능한 등록 원본 `{source_asset_ref, video_stream_ref, duration_sec}`, 등록 순서) 추가. `record_source_registered(source_asset, media_streams=None)`가 `AVAILABLE`이면 저장 |
| `store_state.py` | 위 두 필드를 `_STATE_FIELDS`에 추가 |
| 새 `timeline_source.py` | `CaseTimeline` · `CaseTimelineSource` · `RecordingSequentialTimelineSource` |
| 새 `analysis_start.py` | `start_analysis()` · `reflect_hint_extraction()` · `issue_initial_search()` · fingerprint · 예산 기본값(`InitialSearchBudget`) |
| `command.py` | `START_ANALYSIS` handler, `execute_command(..., timelines=, budget=)` 주입 |
| `service.py` | `receive_hint_extraction_result()`(load · 반영 · save · appended 반환) 추가, 기존 aggregate 수준 `receive_hint_extraction()`은 `analysis_start.reflect_hint_extraction()`으로 흡수 |
| `view.py` | `"description": case.description` |
| case-command 계약 | §11을 정식 판본(§2 표 · §5 · §6)으로 이동, 미결 2 · 3 · 4 닫음 |
| `design-refinement-w7-baseline.md` | 8-1 · 8-16 상태 |

## 5. 테스트

- command: 영상 0개 거부 · 빈 설명 → `COARSE_SEARCH` 바로 · 설명 있음 → `HINT_EXTRACT` · 두 번째 클릭 거부 · 202 `running_jobs`에 발주 job `PENDING` · 거부 시 상태 무변화.
- 반영: OK · ABSTAINED · FAILED 각각 hints · `HINT_EXTRACT` 정산 · scope + `COARSE_SEARCH` 1건 · `case_rev` 그대로 · 진입 함수가 append한 `COARSE_SEARCH`를 돌려줌 · 기다리는 `HINT_EXTRACT`가 없으면(중복 결과) 아무것도 바꾸지 않음 · 실패 시 저장 안 함.
- 설명: 공백만 적은 설명은 원문 그대로 저장 · 구조화 생략.
- 범위: 4개 유형 · `[0, duration_ms]` · 예산 값 · fingerprint 결정성(같은 내용 같은 값, `scope_id` 무관).
- port: 가짜 구현으로 case 로직, 임시 구현은 recording 실제 함수로 영상 1개 · 2개.
- 저장: `description` · `sources` 저장소 왕복. 등록: VIDEO 1개 → ref, 0개 · 2개 → `None`, 스트림 인자 없음 → `None`.
- smoke: 빈 case → 업로드 2개 → `START_ANALYSIS` → 반영 → `COARSE_SEARCH`.

## 6. 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| 영상마다 따로 탐색(범위 · `COARSE_SEARCH` 여러 건) | case당 타임라인 하나라는 아키텍처 결정과 어긋난다. Run이 여러 개라 후보 묶음 투영(#187 변경)이 새로 필요하다 |
| 범위 하나에 영상별 타임라인 구간 여러 개 | AnalysisScope 계약 §10-2가 「한 범위의 구간은 같은 타임라인」을 요구한다(`scope.py` 검증) |
| #313(recording 정렬 기능)이 나올 때까지 전체 보류 · 영상 1개만 지원 | 여러 영상 업로드(#247 H-5)가 이미 제품 흐름이고, 8-1 전체가 다른 모듈 일정에 묶인다 |
| 상황 단서로 유형 좁히기 | 단서 구조화가 유형을 내지 않고, 틀리거나 비면 실제 사건을 아예 못 찾는다 |
| 시간 단서로 탐색 범위 좁히기 | 「6시 반쯤」을 타임라인 위치로 바꾸려면 절대 시각(파일명 시각 후보 · evidence 판단)이 필요하다 — 별도 설계 |
| 타임라인 실패를 탐색 실패 notice로 | 「다시 찾기」 action이 이전 `COARSE_SEARCH` 없이는 동작하지 않아 사용자가 막힌다 |
