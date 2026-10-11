# `search` — 사건 탐색

**Owner:** 서어진 (`docs/management/ownership.md`) · **경계:** `docs/architecture/module-architecture.md` §4-모듈2 · **문서 작업공간:** `docs/modules/search/`

## 이 폴더가 하는 일 (요약 — 원문은 §4-모듈2)

Coarse 후보 구간 생성·Fine/Classification visual verification·4종 event routing·`AnalysisRun` 실행 기록·실패 taxonomy 기록·`providers/`(외부 AI API 호출은 여기서만)

## 이 폴더가 알면 안 되는 것 (§4-모듈2 「알면 안 되는 것」)

신고 규정·Report Type / case stage / 확정 Evidence / 사용자 개인정보 / eval의 존재 / 신고용 mp4 생성 / 평가 전용 분기

## 공개 함수

다른 모듈은 `daesingo.search`가 노출하는 공개 함수만 호출한다.

| 함수 | 입력 | 출력 |
| --- | --- | --- |
| `search_candidates(scope)` | `AnalysisScope` | `CandidateSearchResult(analysis_run, candidates)` |
| `verify_visual(input_ref, target_hint=None)` | `ContractRef`, 선택 `SearchHint` | `VisualVerificationResult(analysis_run, visual_evidence)` |
| `verify_visual_with_stream_context(input_ref, candidate, analysis_source_streams, target_hint=None)` | `ContractRef`, `CandidateEvent`, typed MediaStream facts | `VisualVerificationExecution(result, selected_video_stream)` — 월요일 Real E2E용 비정규 실행 문맥 |
| `build_intent_hint_extractor(api_key).extract(text, case_id=..., prior_hints=None, timeout_sec=60)` | 사용자 자연어 원문, 선택 이전 단서 | `IntentHintResult(status=OK·ABSTAINED·FAILED, 단서 4개, confidence, correction_target, failure_kind, usage)` — 자연어 단서 구조화(#210). 예외를 던지지 않는다. 모델은 `DAESINGO_INTENT_MODEL` |

fixture 기본 동작은 그대로 유지한다. 실제 실행에서는 공개 `SearchService`와 `AnalysisSourceResolver`를 구성하고 `service=`로 주입한다. 제품과 eval 모두 이 경로를 사용하며 `eval_mode`나 GT 접근 분기는 없다.

입력과 출력은 Final Data Contract를 파싱한 불변 Pydantic 객체다. JSON 경계에서는
`model_validate_json`, Consumer 전달 시에는 위 타입을 그대로 사용한다.

## 상태

1차 Mock E2E 통합용 fixture 스텁과 Gemini 실제 구현이 함께 있다. `data/mock/search/scenario_*.json`에 기록된 실행은 기존 기본 경로가 반환한다. Gemini 구현은 Coarse `coarse-p3`, Fine `fine-p3` 리소스 프롬프트와 fingerprint, 구조화 응답 schema, 429 전용 재시도, 업로드 cache, usage/cost ledger를 사용한다. Fine은 네 event type별 검증 지침을 선택하며 기존 `LANE_CHANGE` 입력은 공개 계약의 `SOLID_LINE_LANE_CHANGE`로 변환한다.

독립 실행용 진입점은 다음과 같다. `ELICE_ML_API_KEY`(기존 이름 `GEMINI_API_KEY`도 읽는다 — `config.api_key_from_env`)가 필요하며 결과 JSON의 문자열은 번호판 형식을 마스킹한다.

```bash
uv run python -m daesingo.search coarse --source clip.mp4 --duration-sec 30
uv run python -m daesingo.search fine --source clip.mp4 --duration-sec 30 \
  --event-type SOLID_LINE_LANE_CHANGE
```

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run basedpyright
uv run python data/mock/validate_mock_pack.py
```
