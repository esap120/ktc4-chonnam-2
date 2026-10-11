# Core User Flow cross-module 정합성 검토

## 1. 목적과 결정 원칙

> 이 문서의 제안은 현재 레포의 계약·ADR·구현·Product Flow를 대조하여 작성한 검토용 참고안이다.
> 각 Module Owner의 전문 영역 판단, 기존에 명시적으로 합의된 결정, Producer/Consumer 간 합의가 우선한다.
> 제안과 Owner 의견이 충돌하면 제안을 정답으로 간주하지 않고, 해당 항목을 cross-module 논의 또는 Product Decision 대상으로 올린다.

목적은 PR #145의 의미 변경을 기존 설계와 대조하고, Owner가 결정할 질문과 구현·문서 후속을 분리하는 것이다. 이 보고서는 코드·Contract·ADR을 변경하거나 새 정책을 수락하지 않는다. 상세 근거는 이 문서에, 토론은 말미의 GitHub Issue Draft에 둔다.

- 현재 구현 기준: 원격 `develop`과 동기화한 **`742ca89bd78e5653ca848eaf518c7c9f021a0546`**. 작업 브랜치: `codex/core-user-flow-cross-module-review`. 최초 정적 조사 기준은 `bae28184f9940c0da0bce3fe334a1432920bea97`이며, 이번 갱신은 두 커밋 사이 65개 변경 파일의 영향을 대조했다.
- 최초 조사일: 2026-09-25. **최신 구현·GitHub 논의·무과금 회귀 갱신: 2026-09-27 KST**. 유료 실측 6회의 실행 기준은 계속 **#147 head `032efc0`**이며 최신 develop의 유료 E2E 결과로 소급하지 않는다. 이번 갱신의 유료 호출은 0회다. 요청한 파일명은 유지했다. 일정의 일요일은 **9월 27일**, 월요일은 **9월 28일**이다.
- 기준 PR: [#145][pr145], 2026-09-23 병합. merge commit `24995b86fe89ba09f3c8b9f0a6c26128cf92a840`.
- 판정 순서: **Product 의도 → 현재 Contract/ADR → 실제 구현 → Wireframe/Web → 후속 논의 → 정합성**. 실행 코드나 최신 Product 문서 하나를 모든 영역의 정본으로 취급하지 않는다.
- Accepted 결정을 바꾸는 곳은 **기존 결정 재검토 필요**로 표시한다. 이미 답이 있는 질문, 의도적으로 Deferred한 작업, 새 Flow와 무관한 기존 문제는 다시 결정 요청하지 않는다.
- `UNKNOWN`, 값의 `NEEDS_REVIEW`, 실행 실패, 아직 관찰하지 않음, 사용자가 실제로 모른다고 응답함은 서로 다른 사실이다. 같은 경고 문구나 임의의 `USER_UNSURE`로 합치지 않는다.

분류는 다음과 같다. 한 Decision Point에 서로 다른 층의 문제가 있으면 행별로 복수 분류한다.

| 분류 | 의미 | 처리 |
| --- | --- | --- |
| A | 정합 | 재논의하지 않음 |
| B | 구현 미완성 | 합의된 경계 안의 후속 구현·검증 |
| C | 문서 stale | 최신 결정 링크와 설명·화면 동기화 |
| D | Contract 변경 필요 가능성 | Producer/Consumer가 표현·버전·이행 범위 확인 |
| E | Product / Cross-module Decision | 의미 충돌·공동 정책을 비동기로 논의, 미해결분만 회의 |

## 2. PR #145 변경 요약

### 실제 before/after 고정

`gh pr diff 145`의 **1개 파일, 20개 hunk, +127/-190 전체**를 읽었다. 비교 대상은 현재 파일만이 아니다.

| 구분 | Git 객체 | 확인 |
| --- | --- | --- |
| before | `e7ed4a4858df4ceff4991090c23d316cfe843ceb:docs/product/core-user-flow.md` | blob `6ce9b55a45a8661bbd47346905a147f33d14624b` — 실제 diff의 old blob과 동일 |
| after | `bcab87db7d128696456efd59eaf7183881e20472:docs/product/core-user-flow.md` | blob `ba99239538803b9fe0e7cd479f785bb582d1cce3` — 실제 diff의 new blob과 동일 |
| 최초 / 최신 develop | `bae28184` / `742ca89:docs/product/core-user-flow.md` | 두 기준 모두 PR 이후 의미 변경 없는 동일 after 파일 |

[before 원문][flow-before] · [after 원문][flow-after] · [PR 전체 diff][diff145]. 아래 old/new는 이 diff의 hunk 시작 줄이다. 단순 줄 이동도 확인하되, 마지막 개행 추가는 정책 변경에서 제외했다.

| 추적 ID · old→new | 삭제·이전 의미 | 추가·바뀐 의미 / 사실상 닫은 미결 | 추적 및 판정 |
| --- | --- | --- | --- |
| F01 · 4→4 | 중간 개입 중심의 기존 설명 | 결과 중심 검토 전환일과 “중간 승인 없이 초안, 결과에서 수정” 원칙 추가 | D1·D3·D6, B/D/E |
| F02 · 88→90 | AI 오해를 그 자리의 단서 4칸으로 수정; 구조화 UI 목록의 사건 후보 영상 | 잘못된 이해는 결과에서 수정·후보 변경·재탐색. 독립 후보 영상 항목 삭제 | D1·D8·D10, B/C |
| F03 · 159→160 | 업로드 → 영상정보 확인 → 한계 안내 → 설명 → AI 범위 확인 → 분석 | 홈에서 영상+설명 통합, 구조화 후 바로 분석. 정보·한계의 독립 화면 제거 | D1·D8, B/C. 사실·한계 고지 의무 전체 삭제로 해석하지 않음 |
| F04 · 179→174 | 유력 후보 / 비슷한 후보 비교를 별도 분기 | 후보가 하나 이상이면 최유력 후보 초안 준비 | D2·D6, A/B/D; Fine 결과별 출구는 별도 |
| F05 · 194→186 | 사용자가 사건 선택 또는 보정한 다음 후속 실행 | 후보 종속 정보·신고자료 자동 준비 | D2·D3·D10, B/E |
| F06 · 213→203 | 임계값 미정 동안 **항상 비교**, 사용자 7단계, 별도 시작 동선 | 기본 자동 초안 채택, 순위·최신성 없으면 시작 금지. 읽기 전용 3단계. §4-2 전환표 신설: 원문·기존 후보·초안·완료 작업 보존, 새 탐색 의도/값 수정/후보 변경/실패 구분 | D1·D2·D5·D6·D9·D11, B/C/D/E |
| F07 · 288→293 | “맞아요, 찾아주세요”, 내용·범위 편집, 시간·비용 낭비 방지라는 승인 이유, 원문 인용·미이해 설명 | 중간 계획 승인·수정 없음. 남은 범위 후속 탐색. 근거는 결과의 선택적 “어떻게 정했는지” | D1·D9, B/C/E. 입력을 지어내도 된다는 변경은 아님 |
| F08 · 399→369 | 후보 명시 선택, 처음부터 비교, 화면의 단서 일치 체크 예시, 별도 후보/사건 영상 | Search `rank=1` → Case 자동 선택. 결과에서만 선택적 Top-3. 신고용 영상 중심. 새 후보의 값 재준비, 준비 중 재선택 잠금. 불확실성은 상류 제공 시만 표시, 없으면 원문·관찰 문장 비교 | D2·D3·D5·D8·D10, A/B/C/D/E |
| F09 · 537→462 | 다른 후보에서도 번호판·사용자 확인값 유지, 재판독과 확정값 분리 | 번호판·시각·구간·위치·위반 내용·상황을 새로 준비. 옛 직접 입력은 참고만, 새 후보의 사용자 확인으로 승격 금지. §10 중간 번호판·상황 승인 제거 | D3·D5, E. 같은 절의 시간 보정 유지 문장은 남음 |
| F10 · 855→778 | “이어진 사건 영상 보기” | “신고용 영상 보기” | D10, B/C. 내부 IncidentClip 삭제가 아님 |
| F11 · 928→851 | 남은 확인 항목 체크리스트 | 읽기 전용 작업 진행, 완료 단계 유지, 번호판·overlay 병행, 경과시간. AI ETA·퍼센트 미제공 명시 | D8·D9·D10, A/B/C |
| F12 · 954→882 | 번호판·신고 상황만 필수 확인; 미충족 시 다음 버튼 설명 | 모든 불확실성을 상태·출처와 결과로 전달, 번호판 판독 불가도 결과. 영상·값·신고문을 한 화면에서 검토. 예시 번호판 “사용자 확인됨” → “AI 추정” | D3·D4·D6·D8, D/E. 실제 provenance까지 일괄 AI로 바꾸는 규칙은 아님 |
| F13 · 1010→928 | 원본 비교/정보 수정/“신고자료 만들기” | 문제 수정/다른 후보/선택적 근거 보기, 문제 없으면 직접 handoff. 새 결과 전 새 후보 값 확정 표시 금지 | D5·D6·D8·D10, B/C/D/E |
| F14 · 1061→983 | 복수 후보 → Top-3 비교 | 최유력 후보 초안 후 필요할 때 비교 | D2·D8, A/B/C |
| F15 · 1185→1107 | 기록 예시 “첫 후보 선택”, “Top-3 전체 거절” | “최유력 후보 초안 시작”, “전체 후보 재탐색” | D11, B/C. 자동 동작을 사용자 correction으로 기록하지 않음 |
| F16 · 1208→1130 | 완료 정의의 사건 근거 확인·필요한 사용자 수정 | 최유력 후보 초안·문제 항목 수정으로 변경 | D3·D6·D12, B/E |
| F17 · 1233→1155 | 정상 7단계, 시간 보정 후 끝까지 | 정상 자동 초안, 결과에서 후보 변경, UNKNOWN 번호판 결과→handoff, 실패/0건 복구 **네 완료 경로** | D4·D5·D9·D12, B/D/E. 기존 시간 보정 회귀를 폐기한다는 뜻은 아님 |
| F18 · 1246→1168 | 항상 비교를 평가로 결정할 미결; 번호판·상황만 확인 요구 | 자동 초안 채택 명시, 순위·최신성 선행 조건. AI 추정/확인 필요 결과 표시 허용 | D2·D3·D6, A/D/E. 같은 표의 번호판 UNKNOWN 허용은 **기존 문장 유지** |
| F19 · 1266→1188 | 후속 아이디어 별도 절 없음 | 결과 캐시/이력/연속 후보 변경/승인 모드/ETA는 기본 완료 후 검토. 한 번 바꾼 뒤 준비 완료까지 재선택 금지 | D5·D9·D11, A/B/C. immutable 기록·runtime 캐시 폐기를 뜻하지 않음 |
| F20 · 1278→1215 | 필요한 순간 개입 → 수정·확인 | 결과에서만 개입 → 수정 또는 다른 후보 선택. **사용자 최종 승인**은 유지 | D3·D6·D12, D/E |

특히 #145가 새로 결정하지 않은 것: 번호판 UNKNOWN 허용 방향 자체(기존 §12·§26), 위치 UNKNOWN, 수동 제출, 세 readiness gate의 통합, `NOT_OBSERVED`의 긍정 승격, 사용자 응답 자동 생성, timeout 숫자, 학습 재사용 동의, 최종 영상 규격 완화. 아래 분석은 이들을 새 결정으로 잘못 묶지 않는다.

## 3. 조사 범위

### 자료와 정본

| 층 | 대조 자료 / 구현 | 확인한 경계 |
| --- | --- | --- |
| Product/Design | [Core Flow][flow], [Product Spec][product], [PROTOTYPE-SPEC][prototype-spec], [Wireframe README][wire-readme], `00-flow.png`~`13-handoff.png` **14장 직접 열람**, `apps/prototype/src/**` 화면·machine·mock·reportBody | Product 의도, 옛 명시 확인 UX, 이미지와 설명의 불일치 |
| Ownership/Architecture | [ownership][owners], [Architecture][architecture], [contracts README][contracts]와 아래 Final 계약 | module 문서/실험 제안보다 cross-module Final 결정 우선 |
| Search | [AnalysisScope][scope], [AnalysisRun/CandidateEvent][candidate-contract], [VisualEvidence][visual-contract], Search decisions/failure taxonomy, `search/coarse.py`, Fine 변환·service·budget/deadline 및 관련 테스트 | rank는 run 안의 순위, Fine verification은 별도, scope·span·실패·예산 |
| Case | [Tech Spec][case-spec], [W7 baseline][case-w7], selection/stale/revision/correction/timeout/resume decisions, `domain.py`, `service.py`, `view.py`, `correction.py`, `scope.py`, `jobs.py`, `real_e2e.py`, adapters·테스트 | 선택·재선택·부분 재실행, 원문 보존, 실제 downstream 소비, projection |
| Readout | [Plate/Overlay][readout-contract], [ReadoutRun][run-contract], [Observation][observation], [failure taxonomy][readout-failure], overlay presence 결정, `readout/api.py`·providers 및 테스트 | UNKNOWN/abstain/인프라 실패, best frame, association, overlay 값과 존재 여부 |
| Evidence | [EvidenceRecord/Needs][evidence-contract], [TimeResolution][time-contract], [Requirement/Package][package-contract], [CorrectionRecord][correction-contract], ADR-002/003/005/006/007, safety-report policy v1.1, catalog v2/v3/v4, `assembly.py`·`disposition.py`·`requirements.py`·`policy.py`와 tests | confirmed Evidence와 관찰, 사용자 provenance, 각 gate·renderer·버전 이력 |
| Recording | [SourceAsset/MediaStream][source-contract], [Timeline/AssetSpan][recording-contract], [AnalysisSource/DerivedAsset][asset-contract], local incident/frame/span/asset/time 문서 및 `src/daesingo/recording/**` 해당 capability·테스트 | canonical frame, 원본/IncidentClip/Report Video, asset 사실·좌표·timeline revision |
| Web | [value-state-display][web-display], web-stack 결정, 화면 검증 snapshot 설명, `apps/web/src/contracts/*`, `selectScreen.ts`, 각 Screen·DisplayRow·ProgressPanel·테스트 | CaseView만 소비, 실제 버튼과 전송 경로 구분, null Evidence 대기 |
| Eval/Mock | [Eval README][eval-readme], [2차 checklist][eval-checklist], harness·metrics, `eval/runners/impls/mock_pack.py`, `eval/runners/normalize.py`, scorer 및 `data/mock` 7개 scenario·expected·validators·관련 테스트 | fixture 통과와 제품 E2E/실제 품질 구분, 새 Flow 회귀 누락 |
| Runtime/Usage | [JobRecord/CaseView][caseview], [JobExecution][jobexec], [UsageRecord][usage], Case jobs 및 common lifecycle 테스트 | 취소·부분 결과·재시도·새 Intent·비용 원장, UI 승인과 별개 |
| GitHub | 필수 #106/#122/#123/#145/#146/#149 및 기존 연결 이슈, 최신 병합 #119/#120/#121/#126/#138/#147/#148/#152/#155/#156/#159, 미병합 #157. #138/#146/#147은 review·inline도 재조회 | 최초 본문보다 후속 댓글 우선. #145 댓글/리뷰/inline 0건. #146 conversation 1건·inline 17건·review 11건. #123 종료, #139/#153 후속 합의와 #73 Recording 완료 범위 반영 |

“전수”의 단위는 **#145의 모든 의미 변경과 그 Producer/Consumer 연결**이다. 무관한 과거 실험의 모든 raw prediction을 새로 채점하거나 외부 안전신문고의 현행 법·규칙을 검증한 작업은 아니다. 외부 제출 가능성을 법적으로 보증하지 않는다. Wireframe의 이미지 내용은 직접 확인했고, Web은 코드·기존 테스트로 확인했다. 이번 조사에서 브라우저 E2E를 새로 실행한 것은 아니다.

### 최신 구현 영향 — `bae2818 → 742ca89`, 2026-09-27

Product Flow·Final 계약·ownership·Evidence ADR/구현은 이 범위에서 변경되지 않았다. 따라서 아래 병합을 Q1~Q8의 정책 수락이나 Package gate 해제로 해석하지 않는다. 기존 고정 링크 중 변경 없는 파일은 최초 커밋 링크를 유지하고, 바뀐 구현은 현재 커밋 링크와 이 절로 보강했다.

| 최신 변경 | 기존 보고서에서 갱신한 판단 | 남은 경계 |
| --- | --- | --- |
| [#147][pr147] 병합 — stream context, null 시각 방어, progress | Positive Fine/OCR→Evidence 기록이 이제 develop에 있음. `package_assembly` 일괄 DONE 오류는 수정됨 | dump의 Package 없는 READY, AWAIT 소비 누락, 실제 응답·최종 자산 facts는 미해결. 과거 실측은 `032efc0` 고정 |
| [#138][pr138] 병합 — Readout v1.3, target crop, canonical frame adapter | 발행 version 불일치는 해결. 숫자-only crop 보류·hint 불일치 fallback 차단·RecordingFrameSource 구현을 현재 동작으로 인정 | **새 2줄 partial 회귀 실패**(D4). Case는 여전히 LocalVideoFrameSource 사용(D10). active mock에는 v1.2 표기 5건 잔존 |
| [#152][pr152] 병합 — retry deadline | Coarse/Fine→provider→retry에 같은 deadline 전달; exhausted budget 회귀 PASS | factory 60초 cap과 scope budget 단일화는 #149, 자동 확대 권한은 Q7 |
| [#119][pr119] 병합 — Web notice | 검색 키워드 부재의 직접 검색 안내 mapping·테스트 추가. 위치 UNKNOWN 정책 재논의 없음 | notice Producer 발행부터 브라우저까지의 새 E2E는 미실행 |
| [#120][pr120] / [#121][pr121] / [#126][pr126] 병합 — Readout 연구·Eval | Exact 측정 메타데이터 기준과 candidate/classification 95% Wilson 구간 추가 | plate 정규화 정책·C tier GT 부족, #145 완료 journey 회귀는 별개. 이번 4/5를 정확도로 해석하지 않음 |
| [#148][pr148] 병합 — intake robustness 연구 기록 | prior_hints를 쓰는 실험 설계·원인 분석 보강 | CaseAggregate production intake 배선·결과 수정 journey 완료가 아님(D1) |
| [#155][pr155] / [#156][pr156] 병합 — provider/cost 정리 | ledger provider가 `elice`, dead `fine_reserve_usd`·hardcoded `ProviderUsage.cost_usd` 제거 | Fine AnalysisRun token/cost null 유지. #153의 pricing_id·env 호환 합의는 구현 후속(D11) |
| [#159][pr159] 병합 — Recording benchmark/baseline | 분석/incident 범위 분리·원본 fingerprint·3회 FROZEN 측정 근거 추가 | export/PLATE_IMAGE/REPORT_VIDEO 접합이나 end-to-end SLA를 증명하지 않음(D10) |
| #123 closed / #146 merged / #139·#153 최신 댓글 | 옛 StreamScreen 과제는 종료. #146 후속은 실제 사용자 동선/API·DB·queue/worker E2E. target_hint=None 우선 진행과 pricing 방향은 재질문하지 않음 | #146 merge는 develop→main 통합이며 별도 Flow 정책 변경이 아님. #157은 충돌로 OPEN |

**새로 실행 확인한 문제 2건:** `바5215`가 OK·abstained=false·best_frame 있음으로 나오는 Readout partial guard 실패, real fixture 추가 뒤 Web 고정 개수 assertion 2건 실패. 기존 문제의 미해결/테스트 드리프트이며 새 Product Decision이 아니다. Owner별 초안은 §10에 둔다.

### 직접 실행한 검증

**아래 기존 행은 당시 커밋의 증거다.** 최신 `742ca89` 검증은 표 마지막 행들로 분리한다. 같은 검사라도 범위가 확대됐으므로 293→297→723을 기능 증가량으로 비교하지 않는다.

| 검증 | 결과 | 의미와 한계 |
| --- | --- | --- |
| develop `bae2818` — Python: `uv run --frozen --extra test python -m pytest tests/case tests/evidence tests/readout tests/eval/test_mock_pack_contract.py tests/eval/test_mock_pack_pipeline.py tests/search/test_analysis_run_contract.py tests/search/test_scope_budget.py tests/recording/test_frame_asset_capabilities.py tests/common/test_job_execution.py -q` | **293 passed, 2 skipped** | 정적 조사 당시 기준. `test_real_video_pipeline.py` 2건은 로컬 영상 부재로 skip |
| develop `bae2818` — Web: `npm --prefix apps/web test -- --reporter=dot` | **39 passed** | CaseView 소비·표시 단위 테스트. 실제 command 전송/사용자 완료 경로 증명 아님 |
| #147 head `032efc0` — 같은 Python focused set, `--basetemp`만 별도 scratch로 지정 | **297 passed**, 3 warnings, 37.20초 | #147 source + 동일 lock 계열 환경. `doc/20260620_141956_EVT_1.avi`가 있어 실제 ffmpeg·PaddleOCR 2건도 실행됨. 최초 실행의 3 setup error는 이전 사용자 소유 pytest temp 접근 문제였고 새 basetemp 재실행으로 해소 |
| #147 head `032efc0` — `tests/case/test_real_video_pipeline.py -q` | **2 passed**, 47.91초 | stub Coarse/Fine + 실제 ffmpeg·Recording·PaddleOCR 환경 확인. 유료 provider 검증은 아님 |
| #147 head `032efc0` — Web source를 scratch에서 `vitest run --reporter=dot` | **39 passed** | worktree에는 `node_modules`가 없어 develop checkout의 동일 설치 의존성을 사용. #147 Web source 자체의 단위 회귀 |
| #147 head `032efc0` — `python data/mock/validate_mock_pack.py` | **51 JSON / 7 scenario PASS** | 공용 Mock 정합성. synthetic/mock 범위 |
| #147 head `032efc0` — `python scripts/check_contract_fixtures.py` | **문서 60 / JSON 26 / 의미 104 검사 PASS** | 계약 fixture 검사. 새 Flow 구현·Owner 수락 아님 |
| #147 head `032efc0` — scratch synthetic contract probe | **D2/D3/D4/D5 재현** | Mock Pack 객체를 변형해 public Case/Evidence 경계를 호출. rank/revision 소실, 무응답 Package gate, plate-null 세 gate, READY 재선택·회귀를 확인. 실제 모델 품질 증거 아님 |
| #147 head `032efc0` — `EVT_1` real video + stub Coarse/Fine + 실제 ffmpeg·Recording·PaddleOCR | **16.619초**, `AWAIT_SITUATION_RESPONSE` 뒤 `ContractInputError` | IncidentClip·plate OCR·overlay OCR·TimeResolution·Evidence assembly가 각 1회 호출됐고, 마지막 조립에서 `an uncertain event requires USER_UNSURE context for the v1 fallback`. 유료 호출 0회 |
| #147 기존 실행 기록 — `youtube_clip_01.mp4` real provider + 실제 PaddleOCR | Fine `OBSERVED`, plate `125호1108`, Evidence 조립, CaseView 출력; Package **BLOCKED** | [#147 실험 기록][pr147-positive]의 선행 실행. `occurred_at`과 `situation_response` 부재가 blocker. 이번 세션의 재실행 결과와 혼합하지 않음 |
| #147 head `032efc0` — 승인 후 `python <scratch>/paid_pr147_probe.py` → 원본 `scripts/dump_real_video_caseview.py --video <worktree>/doc/youtube_clip_01.mp4 --out <scratch>/paid-youtube-clip-01-caseview.json` | **real provider 1회 실행**, 25.711초, Coarse/Fine 각 1회, 총 4,464 token, 재시도 0회 | Fine **NOT_OBSERVED** → NOT_ASSEMBLED. 실제 Recording은 실행했지만 IncidentClip/OCR/TimeResolution/Evidence/Package는 음성 종료 때문에 **미실행**. 아래 계측 참조. Positive Package 차단은 이번 재실행에서 재현되지 않음 |
| #147 head `032efc0` — 9/27 `python <scratch>/repeat_probe.py 1`부터 `5`까지, 영상 `youtube_clip_01.mp4`, 각 `--out`은 실행별 scratch | **real provider 추가 5회**, OBSERVED 4 / NOT_OBSERVED 1, 정상 측정 10 calls·15,726 token | Positive 4건은 실제 PaddleOCR/Evidence까지 진행하고 모두 `PackageNotReady`. 계측 실패 후 소모된 별도 Coarse 5 calls·4,984 token도 아래에 공개. 모델 retry는 모두 0회 |
| #147 head `032efc0` — `python <scratch>/audit_repeats.py` | **offline replay**, provider 호출 0회, Positive 객체 20건 validator 오류 0, 요건 8회 동일, Package 거부 4회 동일 | 보존한 실제 입력을 변경하지 않고 재평가. 추가 성공 샘플로 집계하지 않음. 수동 응답·시각·영상 fact를 합성해 Package를 통과시키지 않음 |
| 최신 develop `742ca89` — 아래 Python 확대 회귀 명령 | **723 passed, 1 failed, 3 skipped**, 3 warnings, 61.11초 | synthetic/mock + `EVT_1`의 stub Search·실제 ffmpeg/PaddleOCR 2건 포함. 유료 provider 0회. 유일한 실패는 Readout 2줄 partial; skip 3건은 Recording 실제 영상 opt-in 미설정. 전체 pytest suite를 실행한 것은 아님 |
| 최신 develop `742ca89` — `.venv/Scripts/python.exe -m pytest tests/readout/test_target_crop.py -q -p no:cacheprovider --basetemp <scratch>/pytest-partial` | **5 passed, 1 failed**, 1.34초 | synthetic OCR engine. `바5215` 기대 NEEDS_REVIEW, 실제 OK. 실패 프레임의 객체를 추가 조회해 abstained=false, reason=null, best_frame 존재, version=v1.3 확인. 실제 2줄 영상 새 실행 아님 |
| 최신 develop `742ca89` — `npm --prefix apps/web test -- --reporter=dot` | **38 passed, 2 failed** / 40, 702ms | mock + 커밋된 real JSON 로더/화면 선택 단위 검사. scenario 수 기대 8/실제 9, READY+package 없음 기대 1/실제 4. fixture 증가에 뒤처진 고정 개수 검사이며 새 브라우저 E2E는 아님 |
| 최신 develop `742ca89` — `.venv/Scripts/python.exe data/mock/validate_mock_pack.py` 및 `scripts/check_contract_fixtures.py` | **51 JSON / 7 scenario PASS**, 문서 60 / JSON 26 / 의미 104 PASS | fixture 구조 검사. Readout partial 실패·active mock v1.2 잔존·Web 개수 드리프트를 잡는 검사가 아니므로 통합 PASS로 확대하지 않음 |
| 최종 Report Video export / 실제 handoff | **NOT_RUN** | 음성 2건은 downstream 미실행, 추가 Positive 4건은 Package 거부. 외부 handoff는 실행 범위에 포함하지 않음 |

최신 확대 회귀의 정확한 scope는 다음과 같다. 기존 `.venv`를 사용했으며 `uv sync`·의존성 변경은 하지 않았다. Python/Paddle 버전과 non-conda `C:\ffmpeg\bin`은 아래 과거 실행 환경과 동일하다. 새 lock 전체를 재설치한 검증은 아니며, 현재 `pyproject.toml`은 이제 `readout-paddle` extra로 해당 Paddle 3종을 명시한다. 로그는 로컬 `%TEMP%/daesingo-flow-latest-742ca89/current-focused.log`·`partial.log`에 보존했다.

```powershell
.venv/Scripts/python.exe -m pytest tests/case tests/evidence tests/readout tests/eval/test_mock_pack_contract.py tests/eval/test_mock_pack_pipeline.py tests/eval/test_interval.py tests/eval/test_score_cli.py tests/eval/test_scorer_candidate.py tests/eval/test_scorer_classification.py tests/search tests/recording/test_frame_asset_capabilities.py tests/recording/test_recording_baseline.py tests/recording/test_recording_benchmark.py tests/common/test_job_execution.py -q -p no:cacheprovider --basetemp <scratch>/pytest-full
```

실행 환경은 두 시점을 구분한다. 중단 전 #147 worktree의 새 `.venv`를 lock extras 뒤 Paddle 3종 순으로 구성해 2건을 통과했다. 세션 재개 시 그 venv의 `pydantic/__init__.py`를 찾지 못해 import할 수 없었으므로, 이후 무과금 검증과 유료 실행은 버전이 확인된 메인 `.venv`에서 #147 source를 우선 import해 실행했다. Python 3.12.3, PaddlePaddle 3.3.1, PaddleOCR 3.7.0, OpenCV contrib 4.10.0.84 환경이다. 또한 실행 당시 사용자 프로필의 ffmpeg 8.1 경로 접근이 거부되어 non-conda `C:\ffmpeg\bin`의 Gyan 8.0 static build를 명시했다. 이 차이는 실행 한계로 남기며 제품 판정으로 사용하지 않는다. `doc/real-e2e-protocol.md`는 두 checkout 모두에 없어 #147 본문·실험 기록의 완료 기준을 사용했다.

### 승인 후 유료 1회 실행 — 2026-09-26

정상 2회, transient retry 포함 최대 8 request attempt 계획을 보고하고 승인을 받은 뒤 **영상 1회만 실행**했다. 실제로는 Coarse 1회 + Fine 1회, 재시도 0회였다. Fine run 시작 시각은 `2026-09-26T06:11:26.335345Z`이며 모델은 `gemini-3.8-flash`, Fine prompt는 `fine-p3`다. 동일 영상의 기존 #147 기록은 OBSERVED였지만 이번에는 NOT_OBSERVED였다. provider는 실선 부재·점선 존재로 판정했다. 이것은 **모델의 반환값**이며 사람이 정답 라벨을 새로 확인했다는 의미가 아니다. ffmpeg 등 환경이 달라 이전 실행과 입력 byte·조건이 동일했다고 보장할 수 없으므로 판정 차이의 원인을 확률적 변동 하나로 단정하지 않는다. 원하는 판정을 얻기 위한 반복 실행은 하지 않았다.

| 단계 | wall time | provider latency | input / output / total token | request attempt |
| --- | ---: | ---: | ---: | ---: |
| Recording/탐색 입력 준비 (`PREPARE_CONTEXT`) | 3.949초 | 해당 없음 | 해당 없음 | 0 |
| Coarse | 6.653초 | 6.640초 | 797 / 201 / 998 | 1 |
| Fine | 13.839초 | 13.828초 | 765 / 2,701 / 3,466 | 1 |
| bundle orchestration (**Fine 포함**) | 14.215초 | 위 Fine 참조 | 중복 합산하지 않음 | 위 Fine 참조 |
| 전체 pipeline | **25.711초** | 단계별 값 참조 | **1,562 / 2,902 / 4,464** | **2, retry 0** |

전체 시간은 wrapper의 pipeline 계측 구간이며 초기 Python import 시간은 제외한다. bundle 시간은 Evidence assembly 시간이 아니다. 음성 분기 때문에 실제 assembly 호출은 없었다. SDK usage의 `thought_tokens=0` 표시는 별도 reasoning token 계측 성공을 뜻하지 않는다. **비용은 측정 불가(단가 미설정)**이며 0원으로 해석하지 않는다. Fine provider token은 위와 같이 확보했으나 공개 `AnalysisRun.usage_summary.token_usage`와 `total_cost`는 null이었다(D11, #153).

관찰된 정상 음성 출구는 `Fine.outcome=SUCCEEDED`, `verification=NOT_OBSERVED`, `disposition=NOT_ASSEMBLED`, reason `evidence.visual_event.not_observed`다. 반면 dump 결과는 **`CaseView.stage=READY`, candidate 1개, evidence=null, package=null**이었다. downstream 비조립은 Accepted 결정과 정합하지만 READY projection은 그와 별개의 구현 결함이다(D6). OCR 값 UNKNOWN·사용자 무응답 Package 차단·Readout 실패가 실제 발생했다고 이 결과를 해석하지 않는다. 해당 단계는 호출되지 않았다.

**로컬 재현·보존 근거:** scratch는 `C:\Users\Public\Documents\ESTsoft\CreatorTemp\daesingo-flow-execution-20260926`이다. `paid_pr147_probe.py`는 #147 source를 import하고 원본 dump entrypoint를 실행하며, 계측·실행 바이너리/임시 경로만 주입한다. 키·prompt·media를 로그에 남기지 않았고 커밋된 `data/real/case/`는 덮어쓰지 않았다. repo의 기존 real JSON은 최종 CaseView뿐이므로 중간 객체 replay에 재사용하지 않았다. 무과금 결과는 `no-cost-contract-probe.json`, `await-real-stub-probe.log`, `pr147-focused-pytest-rerun.log`에 보존했다. 이 로컬 파일들은 보고서와 함께 원격 게시된 자료가 아니며, 아래 요약·해시가 이번 문서에 남기는 근거다.

| 보존 파일/입력 | SHA-256 |
| --- | --- |
| `paid-youtube-clip-01-metrics.json` | `B1B30798074EA8F5CAE7878EE0B4E469C7CB69DAF30DCC88235D9E181AFC58FB` |
| `paid-youtube-clip-01-caseview.json` | `5768F3623121F40248CE2700B707A108357D148938553041D93BF1221F85C3A6` |
| 입력 `youtube_clip_01.mp4` | `1A430BA27EB95568BCAA79EB092786EAC9030046C073F09853258BA543BDCD64` |

### 추가 5회 측정과 OBSERVED 검수 — 2026-09-27

사용자의 추가 측정 요청에 따라 같은 원본 SHA-256, #147 `032efc0`, target `SOLID_LINE_LANE_CHANGE`, 모델·prompt·ffmpeg 8.0·Python/Paddle 환경을 유지해 **Coarse부터 다시 실행하는 5회**를 수행했다. 아래 R1~R5는 서로 다른 run이며 Coarse가 매번 span을 다시 제안했다. 따라서 동일 Fine 입력만 고정한 재현성 시험은 아니다. 첫 Positive가 나와도 정한 5회를 모두 기록했고, 표본을 골라 버리지 않았다. 결과는 **OBSERVED 4회, NOT_OBSERVED 1회, UNCERTAIN 0회**다. 작은 단일 영상 반복이므로 4/5를 제품 정확도·재현율이나 안정적인 성공확률로 해석하지 않는다. 9/26 1회까지 합치면 이 세션의 완결된 실측은 6회(OBSERVED 4 / NOT_OBSERVED 2)이며, 별도 선행 #147 실험은 이 분모에 넣지 않는다.

| 실행 | Fine / downstream | Coarse span (초) | 전체 wall | Coarse / Fine provider latency | Coarse / Fine token | input / output / total token |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| R1 | OBSERVED → ASSEMBLE → Package 거부 | 1.000–4.500 | 28.746초 | 3.984 / 9.625초 | 986 / 2,678 | 1,562 / 2,102 / 3,664 |
| R2 | OBSERVED → ASSEMBLE → Package 거부 | 1.000–4.500 | 25.744초 | 3.281 / 8.453초 | 1,007 / 2,494 | 1,562 / 1,939 / 3,501 |
| R3 | OBSERVED → ASSEMBLE → Package 거부 | 0.800–3.800 | 24.969초 | 3.469 / 7.687초 | 995 / 2,272 | 1,562 / 1,705 / 3,267 |
| R4 | NOT_OBSERVED → NOT_ASSEMBLED | 1.200–4.100 | 12.634초 | 2.828 / 7.063초 | 964 / 2,191 | 1,562 / 1,593 / 3,155 |
| R5 | OBSERVED → ASSEMBLE → Package 거부 | 1.000–4.500 | 20.838초 | 4.015 / 3.078초 | 997 / 1,142 | 1,562 / 577 / 2,139 |
| 정상 측정 합계 | Positive 4 / negative 1 | 매번 rank1 1개 | **112.931초** | 위 단계별 계측 | **10 request attempts, retry 0** | **7,810 / 7,916 / 15,726** |

계측 시간은 wall 측정이며 provider latency와 겹치므로 합산하지 않는다. Positive의 IncidentClip 생성은 R1/R2/R3/R5 순서로 **1.180 / 1.218 / 1.157 / 1.163초**, plate API는 **10.995 / 9.871 / 9.781 / 9.528초**였다. plate 시간에는 Paddle 모델 초기화·프레임 처리도 포함한다. overlay API는 모두 반올림 **0ms**였지만 미호출이 아니다. [Paddle provider의 frame/OCR 캐시][pr147-paddle]가 plate와 같은 픽셀 판독을 재사용하므로 독립 OCR 전체 비용으로 읽으면 안 된다. R4는 정상 음성 분기로 IncidentClip·Readout·TimeResolution·Evidence·Package를 호출하지 않았다.

**계측 오류와 총 호출량 공개:** 첫 5회 시도에서는 보고서용 scratch wrapper가 중간 인수를 직렬화하며 service dataclass의 HTTP client까지 `asdict()`로 복사해 TypeError를 냈다. Coarse만 각 1회 호출됐고 Fine은 0회다. repo 코드의 오류나 NOT_OBSERVED가 아니며 분포에서 제외한다. 무과금 직렬화 검사로 고친 뒤 위 5회를 실행했다. 이 시행착오의 token은 순서대로 **1,008 / 988 / 983 / 1,013 / 992**, 합계 **4,984 token**, wall **34.764초**다. 따라서 **9/27 실제 과금 대상 요청은 15회(실패 계측의 Coarse 5 + 정상 측정 10), 20,710 token**이다. 최초 계획의 기본 10회보다 5회 늘어난 이유는 이 계측 오류다. 9/26까지 누적하면 17회·25,174 token이며, 비용은 모두 **측정 불가(단가 미설정)**다. SDK retry와 수동 재측정을 구분한다.

#### OBSERVED 4건의 검수 순서와 확인 결과

| 검수 단계 | R1/R2/R3/R5 실제 관찰 | 판정과 한계 |
| --- | --- | --- |
| Fine | `outcome=SUCCEEDED`, `verification=OBSERVED`, visual type `SOLID_LINE_LANE_CHANGE`, disposition ASSEMBLE | 실행 성공·모델 양성 반환. 법적 판단/전문가 GT 확정은 아님. R4는 같은 대상에 점선 존재·실선 부재를 반환해 NOT_OBSERVED |
| IncidentClip | 후보 span으로 clip 생성 API 성공 | 이 자산 생성 성공과 실제 OCR 입력이 clip 범위였다는 증명은 별개 |
| PlateReadout | SUCCEEDED, observation `125호1108` / OK, abstained=false, `SINGLE_FRAME`, confidence 약 0.99115 | 네 Positive에서 같은 판독값. 모두 `target_association=LOW_CONFIDENCE`, `FALLBACK_ONLY`, hint 없음·track_ref=null이므로 대상 연결 확정까지 뜻하지 않음 |
| 실제 프레임 확인 | source 3.873초 프레임을 추출해 직접 열어 흰색 차량 번호판의 `125호1108`과 bbox `[1121,1006,419,70]` 위치 확인 | 판독 문자의 시각 근거 확인. 모든 프레임의 차량 identity·위반 유형을 수동 GT로 검증한 것은 아님 |
| 후보와 OCR 범위 | 네 건 모두 원본 70%인 3.873초 best frame. R3 후보 종료는 3.800초 | **R3은 후보 종료보다 73ms 뒤** 프레임. [real E2E][pr147-real-e2e]가 IncidentClip ref에 원본 파일을 매핑하고 전체 30/50/70%를 읽는 알려진 단순화가 실제 결과에서도 나타남. clip-local frame provenance로 완료 처리하면 안 됨 |
| OverlayTimeReadout | SUCCEEDED지만 value=null / UNKNOWN, reason `readout.overlay.presence_undetermined`, sample_count=0 | 날짜 줄을 확보하지 못함. 실행 실패나 “영상에 시각이 없음을 확정 관찰”한 상태와 다름 |
| TimeResolution | UNKNOWN, resolved 없음, `time.no_resolvable_source`, overlay 입력은 UNVERIFIED·unused | `occurred_at`을 생성하지 않는 계약대로 동작. 파일명·메타데이터에서 유효 source가 추가되지 않음 |
| EvidenceRecord | `vehicle_number`와 관찰 event를 포함해 조립; `occurred_at`, location, situation_response 없음; correction_refs=[] | 무응답 OBSERVED도 Evidence 조립 가능. 이 실제 사례는 시각 미확보 때문에 **EVIDENCE overall=UNKNOWN**이며, 시각이 채워진 synthetic의 EVIDENCE PASS와 구분 |
| FINAL_PACKAGE | 네 건 모두 overall UNKNOWN, **13 checks = UNKNOWN 10 / WARN 1 / PASS 2** | 아래 개별 blocker 참조. `UNKNOWN`을 `BLOCK` enum으로 바꾸어 기록하지 않음 |
| Package builder | 네 건 모두 `PackageNotReady: package.requirement_not_ready`, Package=null | 단순히 “상황 응답과 시간만 입력하면 완성”이라고 결론 내릴 수 없음 |
| CaseView | 네 건 모두 READY, Evidence 있음, Package 없음, package_assembly=PENDING, running_jobs=[], notices=[] | 기존 D6 READY 전이 결함 재확인. 시간이 null인데 `review_needed=false`, `needs_review=false`라는 출력도 있어 값 부재와 검토 안내 표현은 별도 Consumer 확인 필요 |

**실제 FINAL_PACKAGE 차단 목록:** (1) report video 존재 fact UNKNOWN, (2) 최종 영상의 plate visibility UNKNOWN, (3) 신고문 입력 미완성으로 content_length UNKNOWN, (4) situation_response 미질문 UNKNOWN, (5) 첨부 총크기 UNKNOWN, (6~8) image/video/total count UNKNOWN, (9) occurred_at 부재로 deadline UNKNOWN, (10) time display unresolved UNKNOWN이다. location만 WARN이고 image/video each_size는 PASS다. 여기서 size PASS는 해당 첨부물이 실제 생성·검증됐다는 뜻이 아니다. `basis.asset_refs=[]`, 각 크기 actual=0이며 입력에는 원본 source_asset facts만 있고 제출 자산 facts가 없다. 기존 D10/I4·#47 후속도 독립 blocker임이 드러났다.

**값·출처 검수:** Fine의 target 설명에는 `125오1108`(R1/R5), `125우1108`(R3)처럼 OCR과 다른 문자가 들어 있었다. 실제 Evidence.vehicle_number는 Readout의 `125호1108`을 사용하므로 Search 설명을 plate 정본으로 승격하지 않은 점은 정합하다. 다만 Readout의 낮은 대상 연결 확신은 Evidence `needs_review=false`와 CaseView `INFO_SOURCE_VERIFIED`에 드러나지 않았다. 이는 이번 프레임에서 오판독/다른 차량 오선택을 입증한 것은 아니고, **문자 판독의 신뢰와 차량 연결의 신뢰가 서로 다른데 Consumer가 어느 근거까지 표현하는지**의 문제다. 신규 정책 질문을 늘리기보다 #139와 D4/D10에서 처리한다.

**무과금 재검수:** 각 Positive의 보존 TimeResolution·EvidenceRecord·EvidenceNeeds·두 RequirementReport, 총 20개 객체에 #147 `validate_contract()`를 적용해 오류 0건이었다. 이는 해당 구현 validator 범위이며 모든 Final Contract 의미를 만족하거나 Owner가 수락했다는 뜻은 아니다. 원래 args/kwargs로 EVIDENCE와 FINAL_PACKAGE를 8회 재평가해 dict 전체가 같았고, 원래 builder 호출 4회도 같은 `PackageNotReady`와 reason을 재현했다. 입력값·응답·시각·asset fact를 수정하지 않았다. Package가 없으므로 실제 신고문 완성·최종 export·handoff 검수는 **NOT_RUN**이다.

**보존 경로:** `<scratch>/repeat-20260927-fixed/run-01`~`run-05`에 각 metrics·CaseView·run.log, 상위에 `offline-audit.json`, `plate-frame-3.873.png`를 보존했다. 계측 실패 원본은 `<scratch>/repeat-20260927/run-01`~`run-05`에 그대로 남겼다. scratch의 `repeat_probe.py`·`audit_repeats.py`만 추가했으며 모듈 코드·문서·커밋된 real 결과는 수정하지 않았다.

| 실측 metrics JSON | SHA-256 |
| --- | --- |
| R1 | `F0FB7534D2317D7EBF99486B5534287FB18A863927B615142526E61A17FB17E6` |
| R2 | `59C00EEB555DB6042E574B88FABF5CFAC660F3FD088563E31A2692D3DDB5B1D0` |
| R3 | `19F72E4EA8D1C717E7E50FA518B5263DED4E70A2A36CCD714565434FB1B2DA0C` |
| R4 | `021E42DB297F3F686B9B1202093DC5514DDBA8771593FC3F1E4BD5FF9A7E10B3` |
| R5 | `C87E6B19FBD008694B31B7CE1E93F230A70B684977F20060D13C3F95A654AD45` |

### 정적 예상과 이번 실행의 대조

| Decision | 정적으로 예상한 blocker/판정 | 실제 실행 근거와 남은 한계 |
| --- | --- | --- |
| D1 | 사전 승인 필수 계약 없음; intake 배선 미완성 | intake LLM/사용자 수정 journey 미실행. 정책 판정 유지 |
| D2 | rank·revision 소실, rank1 음성 출구 미정 | synthetic 변환 소실 확인; real Fine 음성 확인. stale 후보의 실제 자동선택까지 재현한 것은 아님 |
| D3 | AWAIT 소비 누락; OBSERVED 무응답 Package 차단 | real-video+stub AWAIT 오류, synthetic gate 확인. 9/27 Positive 4건에서 실제 무응답·시각 미확보·자산 fact 미확보의 Package 차단 확인 |
| D4 | plate-null catalog·builder·renderer gate | synthetic 세 gate 확인. Positive 4건의 OK plate와 LOW_CONFIDENCE association 확인; 실제 UNKNOWN/partial/infra 네 상태와 최종 영상 관찰은 미검증 |
| D5 | READY 재선택 거부, 재탐색 후보 삭제 | synthetic 확인 + 거부 후 CorrectionRecord/case_rev mutation 추가 발견. 유지 범위 정책은 미결 |
| D6 | READY는 Package 필요; 부분 결과 표현 공백 | 실제 Positive 4·negative 2건 모두 Package 없이 READY. 완료 신호의 구현 문제 확인 |
| D7 | location=null/WARN Accepted·정합 | 기존 회귀 통과. 새 실제 location-null Package 생성은 미실행; 재논의 불필요 |
| D8 | 옛 Wireframe/command 미배선 | Web 39 단위 회귀 통과. 브라우저에서 새 journey/handoff 조작은 미실행 |
| D9 | 후보 보존·범위/budget 접합 공백 | D5의 후보 삭제 확인. 실제 cancel/timeout/추가 탐색 유료 시나리오는 미실행 |
| D10 | 시간·실제 export/최종 관찰·handoff 완료 미입증 | Positive 4건의 FINAL UNKNOWN 10개 확인. R3에서는 OCR best frame이 후보 종료보다 73ms 뒤. export/I4 공백을 시간·무응답과 분리 |
| D11 | Usage/재현 가능한 provenance 후속 | provider token 확보에도 Fine AnalysisRun token=null 확인. schema 위반으로 단정하지 않고 기존 #153에 연결 |
| D12 | 새 Flow 회귀 누락 | #147 focused 297/Web 39 PASS. 실제 Positive 4·negative 2, Positive 계약 validator 20건·무과금 요건 replay 8건 확인; 새 완료 journey PASS 아님 |

**정정 기록:** “Positive E2E 증빙 없음”은 develop `bae2818` 범위로 한정한다. 9/26 실행은 음성이었지만 **9/27 추가 5회 중 4회가 Positive로 진행해 Package 차단을 직접 재현**했다. 또한 차단 원인을 시간·무응답 두 가지로만 요약하면 불완전했다. 실제 FINAL에는 report video·첨부 facts·최종 plate 가시성 관찰도 없어 총 10개 UNKNOWN이 있었다. 이 항목들을 D10의 별도 구현 의존성으로 보강했다. synthetic 결과도 유효한 Producer 전체 출력/실제 OCR 실행으로 확대하지 않으며 Q1~Q8의 미결 정책은 유지한다.

### 추가 실행 제안 — 이번에는 실행하지 않음

| 목적 | 필요한 영상/입력 | 예상 호출 수와 한계 |
| --- | --- | --- |
| OBSERVED 뒤 시각·상황 응답·Package gate 분리 | 위반 유형과 오버레이 시각을 사람이 확인한 블랙박스 영상 1개 | Coarse 1 + Fine 1 = 2, 현재 retry 상한 포함 최대 8 attempt. 양성 판정은 보장 못함. 중간 객체를 보존하면 이후 gate 비교는 synthetic 무과금으로 가능 |
| 복수 후보 선택·revision·재선택 비용 검증 | 서로 다른 차량/장면 후보가 2개 이상인 영상 | Coarse 1 + 두 후보 Fine 각 1 = 3, retry 포함 최대 12 attempt. 자동 다음 후보 순회 정책을 채택한다는 뜻은 아님 |
| 네 plate 상태를 실제 Readout으로 구분 | 동일 판정 기준의 영역 보임/부분 판독/영역 없음 clip 각 1개; 실행 실패는 별도 fault injection | Readout-only면 유료 Search 0회. 전체 경로까지 실행할 때 영상당 기본 2/max 8 attempt. 실패 주입은 영상 상태와 분리 |
| real Positive Package→export→handoff 검증 | 실제 사용자 응답·확정 시각과 최종 영상 관찰 근거가 확보된 위 양성 실행 | 보존 중간 객체가 충분하면 추가 Search 0회. I4 Producer/export capability가 없으면 영상만 추가해도 완료 불가. 외부 handoff는 별도 범위 확인 필요 |

위 수치는 현재 재시도 설정을 적용한 계획값이며 예약·추가 실행 승인이 아니다. 동일 영상을 원하는 Fine 판정이 나올 때까지 반복하지 않는다.

## 4. Executive Summary

**최신 구현 반영:** #147 Positive 증거·정확한 package progress, #138 런타임 v1.3/target crop/frame adapter, #152 retry deadline, #119 위치 검색 안내는 develop에 반영됐다. 반면 **현재 회귀는 Python 723 PASS / 1 FAIL / 3 SKIP, Web 38 PASS / 2 FAIL**이다. Readout 2줄 partial guard와 Web fixture 개수 검사를 후속으로 추가했다. 기존 상황 응답·plate-null Package·후보 값 승계·부분 결과 상태·자동 범위의 정책 질문은 이번 병합으로 닫히지 않았다. 유료 6회 실측은 #147 기준의 과거 증거다.

아래 네 그룹을 실행 관점으로 다시 묶으면 **즉시 정합=A(D7 및 D2/D9/D10의 기존 원칙), 문서 stale=C(D8·D11), 구현 후속=B(D1·D2·D9·D10·D12), Contract 변경 후보=D(D2·D4·D5·D6), 월요일 Product Decision 후보=E(D3+D6·D5·D9)**다. D4의 넓은 허용 방향은 이미 Owner 답변이 있으므로 미결 정책으로 되돌리지 않는다.

실측은 이 분류를 뒤집기보다 구현 경계를 좁혔다. D2 rank/revision 소실, D3 AWAIT 소비 누락, D4 현행 Package 세 gate, D5 거부된 재선택의 부작용, D6 Package 없는 READY는 확인됐다. **9/27 추가 5회는 OBSERVED 4 / NOT_OBSERVED 1**이며 Positive 4건 모두 실제 OCR·Evidence까지 진행한 후 Package에서 막혔다. 시간·실제 응답뿐 아니라 제출용 자산 facts와 최종 영상 관찰도 없었다. 낮은 차량 association과 후보 밖 OCR frame은 #139/기존 clip 배선 후속의 실측 근거다. D1 사용자 journey, 실제 plate 실패 네 상태, Report Video/export/handoff, Web command 연결은 여전히 미실행이다. Fine AnalysisRun token/cost의 관측성 후속도 #153에 남는다.

### ① Flow 그대로 유지 가능 — 즉시 정합·문서 stale·구현 후속

- **자동 구조화 후 분석 시작**은 AnalysisScope에 승인 필드가 없어 계약 자체와 충돌하지 않는다. 실제 intake LLM 배선·원문 저장·예산 처리와 옛 화면 정리가 필요하다(D1).
- **Search가 순위를 결정하고 Case가 선택하며 Web은 표현**한다는 방향은 정합한다. `rank=1` 의미·stale 제외 원칙은 다시 결정하지 않는다. projection과 자동 orchestration은 미완성이다(D2, #122).
- **위치 `location=null` + WARN Package + handoff capabilities 유지**는 Accepted ADR-003과 구현·테스트에 이미 있다. 재논의 불필요(D7).
- 시간 fallback의 검토 상태, 원본 보존, IncidentClip/Report Video 분리, 부분 재실행, 새 사용자 Intent의 새 Job, WARN 표시, 자동 제출 금지는 유지한다(D8~D11).

### ② Flow는 유지하되 Contract 수정 필요 — Contract 변경 후보

- 후보 `rank`를 CaseView에 싣거나 순서 보장을 명문화하는 #122 접합부. 최신 run/timeline provenance를 Case 안에서 잃지 않는 구현도 필요하다(D2).
- **번호판 식별 실패를 UNKNOWN 경고로 허용하는 Product 방향은 9/25 Evidence/Product Owner 댓글에서 이미 제시됐다.** 현행 필수 plate 입력·rule·renderer는 미반영이다. nullable/누락 표현, 최종 영상 가시성 fact의 처리 범위를 계약화해야 한다(D4).
- Package 이전에도 결과를 보여주려면 부분 결과·대기 사유·허용 action의 CaseView 표현이 필요하다. 단순히 `READY` 의미를 넓혀 해결할 수 없다(D6).
- READY에서 후보 변경, 응답/최종 확인 command, plate preview/export 접합은 현재 계약·구현 범위보다 넓다. 기존 #106/#47을 확장하되 중복 이슈를 만들지 않는다(D5·D8·D10).

### ③ Product Decision 필요 — 월요일 후보

- **D3+D6:** 실제 상황 응답을 결과에서 받을 것인가, Package 전 필수 응답 자체를 없앨 것인가? ADR-005의 명시적 재검토 트리거가 발생했다. 응답 전 독립 작업 허용과 Package gate는 별도로 결정해야 한다.
- **D5:** 후보 변경과 “조금 전/후” 재탐색에서 옛 직접 입력을 어느 context까지 적용할 것인가? 새 Flow 안에도 서로 다른 유지 규칙이 남아 있다.
- **D9:** 남은 범위 자동 탐색은 이미 위임한 scope/budget 안인가, 새 범위·비용까지 자동 확대하는가? 현재 §6과 §22의 문구를 하나의 실행 경계로 맞춰야 한다.
- D2의 rank1 Fine 음성/불확실 결과 출구, D4의 “관찰 결과 없음”까지 WARN으로 풀지 여부는 먼저 해당 기존 논의에서 비동기로 닫는다. 닫히지 않고 기본 Flow를 막을 때만 위 안건에 합친다.

### ④ Flow 자체를 재검토할 후보

**결과 중심 방향 전체를 되돌리자는 제안은 아니다.** 현재 근거에서 비용이 큰 부분은 “사용자 응답·발생시각·최종 영상 사실이 없어도 항상 완성 Package를 먼저 만든다”는 강한 해석이다. confirmed-only Evidence, ready-only Package, 실제 응답 provenance, 최종 영상 관찰 입력을 함께 바꾸게 된다. **부분 결과를 먼저 보여주고 실제 응답 후 Package를 완성하는 해석**이 현재 계약과 더 가까워 보인다(D3·D6).

분석 전 일괄 확인을 복원할 근거는 아직 부족하다. 다만 자동 범위 확대가 예산 경계를 넘는다면, 전체 승인 화면 복원보다 **추가 탐색 의도만 명시적으로 받는 안**을 우선 검토한다(D1·D9). 후보 변경 때 옛 번호판을 무조건 유지하는 안도 현재 차량 identity 근거가 없어 기본안으로 권하기 어렵다(D5·#139).

## 5. Decision Point별 상세 분석

### D1. 분석 전 AI 이해·탐색 범위 확인 제거

#### #145 변경

F01~F03·F06·F07. 업로드와 설명을 한 번 제출하면 구조화 후 바로 분석한다. 기존 §6의 시간·비용 낭비 방지 목적과 4칸 inline 편집은 제거됐다. [before §6][flow-before]와 [현재 §6][flow]를 대조했다.

#### 현재 계약/ADR

[AnalysisScope][scope]는 Case가 만드는 Search 입력이며 `time_ranges`, 대상 유형, hint, `max_cost_krw`/`max_latency_sec` 등의 budget을 정한다. **사용자 승인 완료를 필수 입력으로 요구하지 않는다.** 검색 기억 단서는 확정 Evidence가 아니며 [TimeResolution §5][time-contract]의 `TIME_HINT_EDIT`도 최종 발생시각 근거가 아니다.

Case의 [intake 강건성 결정][hint-decision]은 모순 슬롯의 마지막 값+low, 도메인 밖 입력의 null/low 표현을 정했다. [#144][pr144]가 초기 모델 결정을 교체했으므로 옛 GPT-5 Nano 결정을 다시 묻지 않는다. 이 모델 결정과 실사용 intake 배선은 별개다.

#### 현재 구현

`CaseAggregate.intake()`는 넘겨받은 구조화 hints를 저장한다. `case/scope.py`는 제공된 범위·유형·budget으로 계약을 구성한다. [W7 §3][case-w7]와 #144는 실제 LLM 호출·원문 저장 배선이 아직 없음을 명시한다. **운영 중이던 LLM 수정 기능을 삭제한 회귀로 볼 근거는 없고, Prototype의 편집 경로가 Product에서 제거된 것**이다. [ScopeScreen 및 machine][prototype-machine]에는 기존 확인 후 START_SEARCH 경로가 남는다.

**최신 영향:** #148은 [강건성 연구/spotcheck 기록][latest-intake-research] 보강이며, production CaseAggregate 배선은 여전히 별도라고 명시한다. intake 승인 제거의 정합성 분류는 유지한다.

#### 충돌

- **B:** intake→구조화→scope→발주와 원문/추출값/correction 연결은 구현 후속이다.
- **C:** PROTOTYPE-SPEC·ScopeScreen·Wireframe 00/04/07의 분석 전 승인 동선이 stale하다.
- **E는 D9로 한정:** 잘못 추출된 hint가 결과 재탐색만으로 충분히 복구되는지는 사용자 품질 문제이며, 자동 추가 비용까지 허용됐다는 근거는 없다. 기존 budget 계약을 없애지 않는다.

#### 제안안 — 참고

현재 근거 기준으로 **기본 경로의 사전 확인 제거를 유지**하는 안을 제안한다. raw description→추출 hints→AnalysisScope 참조를 Case가 보존하고, 결과에서 수정한 것이 최종 사실 수정인지 Search hint 수정인지 구분한다. low/null을 확정 단서로 바꾸지 않으며, 범위를 넓힐 때는 D9의 budget 경계를 적용한다.

근거: Scope에는 승인 gate가 없고, 원문 보존은 새 §4-2 요구이며, Case 강건성 결정도 불확실성 보존을 전제로 한다. 영향: Case intake·logging·scope, Web 홈/결과 편집, Eval 잘못된 구조화 후 복구 테스트. 이 제안은 참고안이며 Owner 판단과 cross-module 합의가 우선한다.

#### Owner 질문

독립 정책 질문 없음. Case @yuusoyeon은 D9에서 **위임 범위와 추가 탐색 경계**만 확인한다. 모델 재선정이나 “rank=1 가능 여부”와 묶지 않는다.

#### 결정 상태

**B/C.** 사전 승인 없는 기본 Flow는 유지 가능. 자동 확대 범위는 D9 미결.

### D2. `rank=1` 자동 선택·최신성·Fine 결과

#### #145 변경

F04~F06·F08·F14·F18. 항상 비교하던 잠정 UX를 자동 초안으로 바꿨다. 순위 없는 후보·최신이 아닌 후보로 Case/Web이 임의 선택하면 안 된다.

#### 현재 계약/ADR

[CandidateEvent §4·불변조건][candidate-contract]의 `rank`는 **해당 Run 결과 안의 authoritative ordering**, 1부터 시작하는 중복 없는 순위다. `ranking_score`는 선택적 진단값이며 법적 확신도/선택 임계값이 아니다. `search/coarse.py`는 정렬 결과에 rank를 부여한다. 최신성과 rank는 별도 축이다.

[CaseView][caseview]에는 `selected`, `stale_revision`, `at_provenance`는 있으나 `rank`와 개별 `uncertainties`는 없다. `stale_revision`은 timeline revision 비교이지 “여러 run 중 최신 검색 의도”를 대신하는 필드가 아니다. [#122 최신 댓글][i122-latest]은 자동 선택 책임·stale 제외·Web 재계산 금지를 정리하고, **명시적 rank 투영을 추천**하지만 Consumer 합의까지 완료된 것으로 표시하지 않는다.

#### 현재 구현

[Case service][case-service]의 변환은 후보 ID·summary·thumbnail 등을 옮기지만 rank와 span의 timeline revision을 넘기지 않는다. [Candidate 모델][case-domain]에는 `timeline_revision=1` 기본값이 있어 이 경로로 revision 정보를 잃을 수 있다. [view][case-view-code]는 받은 배열 순서를 유지하고 전달된 timeline revision과 비교한다. **배열 순서가 우연히 맞는 것과 계약으로 보장되는 것은 다르다.**

**정적으로 예상한 blocker / 실제 발생한 blocker:** #147 head에서 raw candidate에 `rank=7`, `span.timeline_revision=9`를 넣어 `receive_search_candidates()`를 호출했다. 변환된 Case `Candidate`에는 rank 속성이 없었고, timeline revision은 입력 9가 아니라 기본값 1, `stale_revision=false`가 됐다. 따라서 **Consumer 변환 경계의 필드 소실**은 synthetic 실행으로 확인됐다. 다만 단일 후보 `rank=7`은 완전한 유효 AnalysisRun을 뜻하지 않고, 필드 전달 여부만 확인하기 위한 sentinel 입력이다. 이 결과는 #122의 기존 접합부를 실행으로 보강한 것이며 새 ranking 정책 결정이나 실제 stale 자동선택 재현은 아니다.

**최신 영향:** `742ca89`까지 Candidate 모델·service 변환 및 CaseView rank 계약에 이를 해결하는 변경은 없다. 과거 synthetic 결과와 현재 diff 대조에 근거한 미해결 판정이며, 최신 커밋에서 실제 stale 자동선택을 새로 발생시킨 결과는 아니다.

승인 후 real-provider 실행에서도 Coarse가 후보 1개를 만들고 Fine이 `NOT_OBSERVED`를 반환했다. 즉 rank1이 Fine 양성을 보장하지 않는다는 계약 구분은 실제 실행에서도 나타났다. 그럼에도 dump가 `READY`를 출력했으므로 음성 결과의 사용자 출구와 Case stage projection은 Q2/D6의 실제 구현 공백으로 남는다. 이 한 번의 결과로 자동 다음 후보 순회 필요성이나 모델 품질을 결정하지 않는다.

`receive_candidates()` 다음 명시적 `select_candidate()`를 호출하는 현재 도메인·테스트 경로에 일반적인 “최신 유효 rank1 자동 선택” orchestration은 없다. Real E2E의 특정 후보 인수/스모크 편의 경로도 이 정책을 구현했다는 증명이 아니다.

Fine은 rank와 별개로 `OBSERVED / UNCERTAIN / NOT_OBSERVED`를 돌려준다. [ADR-007][adr007]·[#142][pr142]로 NOT_OBSERVED는 downstream 비조립 종료가 확정됐다. **rank1이면 Fine 양성이라는 계약은 없다.** 자동으로 다음 후보를 반복 평가해 “첫 OBSERVED”를 찾는 정책은 #145나 #142가 정하지 않았다.

#### 충돌

| 항목 | 판정 |
| --- | --- |
| Search ranking 권한, Case 선택, Web 비판단, stale 제외 | **A**, 이미 답 있음 |
| Case rank·run·timeline provenance 보존, 자동 selection→후속 발주 | **B** |
| `candidates[].rank` 추가 vs authoritative 순서 보장 및 Consumer 검증 | **D**, #122에서 마무리 |
| 여러 run/과거 후보를 보존할 때 현재 선택 대상 집합; rank1이 음성일 때 결과 출구 | **D/E**, 기존 ordering만으로 답할 수 없음 |

#### 제안안 — 참고

**명시적 rank 투영을 기본안**으로 제안한다. Case가 현재 분석 의도에 속한 유효 후보 집합을 먼저 정하고, 그 집합에서 Search ordering을 소비한다. rank 누락·revision 불일치를 배열 첫 항목으로 우회하지 않는다. Web은 주어진 rank/selected/status만 표현한다.

음성 후보는 ADR-007대로 종료하고, 기본안은 **음성 이유와 다른 후보 출구를 결과 맥락에 표시**하는 것이다. 자동 다음 후보 순회는 추가 Fine 비용과 중단 조건을 정한 뒤 별도로 도입한다. 근거: rank는 Coarse 순위이고 Fine 양성을 보장하지 않으며 #142는 자동 순회를 범위 밖으로 남겼다. 영향: Search 계약의 ranking 재설계는 불필요, Case projection/선택, Web 표시, Eval stale·음성 테스트. Owner 합의가 우선한다.

#### Owner 질문

**Q1 — Case @yuusoyeon, Web @uminshin, Search @kong2488-star 확인:** #122의 `rank` 명시 투영안을 채택할지, 순서 보장만으로 닫을지 결정해 달라. 함께 **현재 선택 대상 run의 식별 기준**을 명시하면 과거 후보 보존과 충돌하지 않는다. stale 제외 자체는 이미 #145가 요구하므로 다시 묻지 않는다.

**Q2 — Product @flosure23, Case @yuusoyeon:** rank1 Fine=NOT_OBSERVED이면 음성 결과+다른 후보 출구로 기본 경로를 끝내는 것으로 충분한가? 자동 다음 후보 순회를 원하면 기존 #142 범위를 넘는 별도 결정임을 표시해 달라. D3/D6의 결과 상태 논의와 함께 비동기로 답하면 된다.

#### 결정 상태

**A+B+D, Q2만 E 가능.** #122에서 처리. 자동 rank semantics를 월요일에 처음부터 다시 논의하지 않는다.

### D3. Fine `UNCERTAIN`, 실제 `situation_response`, 실행 순서

#### #145 변경

F05·F09·F11·F12. 중간 상황 확인 없이 끝까지 준비한다. 반면 현재 Flow §15의 상황 응답 UI는 남아 있어 **위치를 결과로 옮기는지, 필수 응답을 없애는지**가 명확하지 않다.

#### 현재 계약/ADR

[ADR-002 §5.9][adr002], [ADR-005 §5.4][adr005], [EvidenceRecord][evidence-contract]는 실제 사용자 응답을 구분한다. `NOT_ASKED`는 `USER_UNSURE`가 아니다. ADR-005 D2-c는 Package 전 사용자 확인 gate를 유지했고, **§8·§15 UX가 바뀌면 기존 ADR을 고치지 말고 새 결정으로 기록**하도록 명시했다. 또한 사건 영상의 적합성은 옛 §8 사용자 선택의 입력 전제였다. 자동 선택 이후 이 전제를 어떻게 최종 검토로 연결할지도 함께 다뤄야 한다.

**기존 결정 재검토 필요.** [9/25 Product/Evidence Owner 답변][r146-situation]은 무응답을 USER_UNSURE로 생성하지 말 것에 동의하면서도, “모든 downstream 정지+옛 확인 화면 복원”을 선결하지 않고 응답 시점과 선행 작업 범위를 공동 결정하자고 정정했다.

#### 현재 구현

| 입력/단계 | 현재 경계와 실제 결과 |
| --- | --- |
| Fine NOT_OBSERVED | `classify_visual_evidence` → NOT_ASSEMBLED; 두 Real E2E 경로가 후속 IncidentClip/Readout/TimeResolution/Evidence 전에 종료. VisualEvidence/Fine Usage 보존 |
| Fine UNCERTAIN + 무응답 | [disposition][disposition] → AWAIT_SITUATION_RESPONSE. null event를 confirmed Evidence로 조립할 근거 없음 |
| Fine UNCERTAIN + 실제 USER_UNSURE | event type null의 제한적 Evidence 조립, generic 표현·WARN 경로 가능. 다른 요건까지 충족해야 Package 가능 |
| IncidentClip / plate OCR / overlay OCR | 입력은 span·clip·frame 등이다. 함수 계약에 situation_response는 없음. 응답 전 관찰 실행 자체와 Package 허용은 같은 gate가 아님 |
| TimeResolution | 관찰·CorrectionRecord 기반 순수 해석. situation_response 불필요. 시각 없음은 UNKNOWN으로 유지 |
| EvidenceRecord | UNCERTAIN/null event에서 실제 USER_UNSURE 없이 `_event_values`가 거부. OBSERVED/non-null은 무응답 상태에서도 조립 가능 |
| RequirementReport | FINAL_PACKAGE의 `package.evidence.situation_response`는 absent/NOT_ASKED → UNKNOWN. OBSERVED도 무응답이면 Package는 막힘 |
| ReportPackage / 신고문 | [builder][requirements]와 [renderer][renderer]가 다시 실제 CONFIRMED/CORRECTED 또는 null-type의 USER_UNSURE를 검사 |

[real_e2e.py][real-e2e]의 두 소비 지점(347, 686 부근)은 NOT_ASSEMBLED만 분기한다. [Case Owner 분석][r146-case-await]도 같은 경로를 지적한다.

**정적으로 예상한 blocker:** AWAIT가 뒤의 clip/OCR/time으로 흘러가고, `situation_response=None`을 넣은 Evidence 조립에서 오류가 난다.

**실제로 발생한 blocker:** #147 head의 `EVT_1`에서 Coarse/Fine만 stub으로 `UNCERTAIN`을 만들고 나머지를 실제 실행했다. 16.619초 동안 IncidentClip, plate OCR, overlay OCR, TimeResolution, Evidence assembly가 각각 1회 호출됐고, 마지막 조립에서 `ContractInputError: an uncertain event requires USER_UNSURE context for the v1 fallback`이 발생했다. `classify_visual_evidence()`가 돌려준 값은 `AWAIT_SITUATION_RESPONSE`와 `evidence.visual_event.situation_response_missing`이었다. 따라서 **AWAIT 소비 누락(B)은 실행으로 확인**됐다. 다만 이 실행은 유료 Fine이 아니라 stub Fine이므로 실제 모델의 UNCERTAIN 발생률을 말하지 않는다. 이 버그가 “모든 관찰을 멈추는 것이 확정 정책”이라는 증거도 아니다.

OBSERVED + 무응답 synthetic probe에서는 EvidenceRecord와 EVIDENCE `PASS`가 성립했지만, FINAL의 `package.evidence.situation_response`와 `package.report.content_length`가 `UNKNOWN`이 되어 overall `UNKNOWN`, builder는 `package.requirement_not_ready`를 반환했다. ready report를 강제로 대입한 방어 경계에서는 `package.input.situation_unconfirmed`, renderer에서는 `report.input.situation_unconfirmed`가 각각 발생했다. 즉 **관찰·Evidence 조립 가능**과 **Package 발행 가능**은 실행에서도 분리됐다.

9/27 real Positive 4건은 실제 plate OCR·TimeResolution·Evidence 조립까지 진행하고, situation_response가 없는 채로 Package builder의 `package.requirement_not_ready`를 재현했다. 이때는 발생시각도 없어 **EVIDENCE overall부터 UNKNOWN**이었다. 따라서 synthetic의 PASS를 real 결과에 옮기지 않는다. 실제 FINAL UNKNOWN 10개 중 무응답 외에 시간·제출 영상·첨부 facts·최종 plate 관찰 공백도 있으므로, 상황 응답 위치 하나를 정한다고 Package 완료가 보장되지 않는다(§3 검수표·D10).

#### 충돌

- **B:** AWAIT를 일반 assembly 실패로 흘리지 않는 안정적 대기/부분 결과 소비가 필요하다.
- **E:** 실제 사용자 응답 없이 Package 발행까지 허용하면 Accepted ADR-005를 뒤집는다. OBSERVED에도 영향이 있다.
- **D:** Evidence가 아직 없을 때 실제 응답을 입력받고 부분 관찰을 보여줄 CaseView/command가 없다(D6·#106).

#### 제안안 — 참고

현재 근거로는 **관찰과 Package gate를 분리하는 A안**이 가장 정합적으로 보인다.

| 안 | 장점 | 단점 | 영향 |
| --- | --- | --- | --- |
| A. 독립 clip/OCR/time은 진행, 부분 결과에서 실제 응답 후 Package 완성 | 중간 승인 화면을 줄이며 실제 provenance·ready-only Package 보존 | “처음 결과는 항상 완성 Package”라는 문구 수정 필요 | Case 대기 소비·부분 결과, Web 응답 command, Product/ADR의 응답 위치 명확화 |
| B. 상황 응답 전 모든 downstream 대기 | 비용 절약, 기존 gate를 보수적으로 유지 | #145 결과 중심 의도와 멀고 기다림 재발 | Flow에 예외 확인 단계 필요; Case/Web 대기 동선 |
| C. 무응답에서도 미확정 generic Package 허용 | 가장 강한 결과 우선 UX | USER_UNSURE와 다른 provenance·정책·template·계약 필요 | Evidence/Requirement/Package/CaseView/ADR 전반 변경 |

A안에서도 NOT_OBSERVED는 선행 관찰 대상으로 확대하지 않는다. “사건 선택”·“상황 응답”·“전체 최종 검토”를 같은 CONFIRMED로 합치지 않는다. Report Video의 사후 각인은 확정된 시각 근거 이후다(D10). 이 제안은 참고안이며 Owner 판단과 cross-module 합의가 우선한다.

#### Owner 질문

**Q3 — Product/Evidence @flosure23, Case @yuusoyeon, Web @uminshin:** 결과 화면에서 실제 상황 응답을 받은 뒤 Package를 완성하는 A안을 기본 경계로 삼을 수 있는가? 응답 전 IncidentClip/OCR/TimeResolution 허용 범위와, 자동 후보 선택이 잃은 옛 §8 입력 확인 전제를 최종 검토 어디서 충족할지 함께 정해 달라. 기존 USER_UNSURE의 실제 provenance 원칙은 재논의하지 않는다.

#### 결정 상태

**B와 E를 분리.** 버그는 후속 구현, 응답 gate 의미는 기존 결정 재검토 필요. #146 최신 댓글을 기준으로 D6과 묶어 비동기 검토한다.

**최신 영향:** #147 병합은 stream/null/progress를 보강했지만 `real_e2e.py` 두 경로의 `NOT_ASSEMBLED` 단독 분기와 `situation_response=None`은 남는다. Evidence disposition/assembly/requirements는 최초 기준 이후 변경되지 않았다. AWAIT 오류의 과거 실행 근거는 유효하며 최신 정책 수락이나 버그 수정으로 바꾸지 않는다.

### D4. 번호판 UNKNOWN — 값 부재와 최종 영상 사실은 별개

#### #145 변경

F08·F12·F17은 번호판 판독 불가도 결과→handoff 경로에 포함한다. **UNKNOWN 허용 방향 자체는 before §12·§26에도 있었다.** #145가 기존 Product–Contract 불일치를 실행 완료 경로로 더 명시적으로 드러냈다.

#### 현재 계약/ADR

[Readout 계약][readout-contract]은 UNKNOWN, NEEDS_REVIEW+abstained, best_frame과 association을 이미 표현한다. [Observation][observation]은 UNKNOWN/ERROR/NOT_APPLICABLE의 `value=null`을 요구한다. [ADR-006][adr006]은 부분 문자열을 임의로 버리거나 형식 불일치만으로 hard reject하지 않고 검토 필요로 보존하는 정책이며, 구현 pending이라고 명시돼 있다.

하지만 [ADR-002][adr002]·현 catalog와 Package는 아래와 같다.

| 층 | 현재 규칙 |
| --- | --- |
| EvidenceRecord | 확정 가능한 `vehicle_number`만 승격. missing은 필드 부재; 값으로 문자열 `"UNKNOWN"`을 넣는 계약 아님 |
| `evidence.vehicle_number.present` | 값 있음 PASS / 부재 UNKNOWN |
| `package.vehicle.plate_visible_in_report_video` | 최종 REPORT_VIDEO 관찰 true PASS / false BLOCK / 관찰 없음 UNKNOWN |
| overall | BLOCK > UNKNOWN > WARN > PASS. 번호판 외 다른 요건도 독립적으로 판정 |
| Package gate | 현재 basis의 FINAL_PACKAGE PASS/WARN, 실제 사용 가능 report video 등 + builder 입력 검증 |
| `report_inputs.vehicle_number` | 현재 `string` 필수. `occurred_at`도 RFC3339 필수 |
| renderer / template | plate non-empty 필수. specific/generic × 위치 유무의 네 template 모두 차량번호 문장을 전제 |
| CaseView/Web | 값 부재 INFO_UNKNOWN 표현은 가능. `package.report_fields`는 null 표시도 가능하지만 upstream Package의 plate 필수성을 해소하지 못함 |

#### 현재 구현 — 네 상태를 합치지 않는다

| 실제 상황 | 현재 Readout 표현/구현 | Evidence·Package 영향 | 조사 결론 |
| --- | --- | --- | --- |
| 1. 번호판 영역은 보이나 문자 판독 실패 | 성공한 판독의 null UNKNOWN 또는 실패 원인에 따른 NEEDS_REVIEW+abstain 가능. best frame 유무는 별도 | usable plate 승격 안 됨 → plate 부재 UNKNOWN. 영역 존재가 최종 영상의 식별 가능 fact를 대신하지 않음 | “실행 성공·값 없음” 가능 |
| 2. 일부 문자만 읽힘 | #138의 숫자-only target crop은 NEEDS_REVIEW·abstain. 2줄 하단 `바5215`용 PARTIAL_PLATE_READ guard도 추가됐으나 **현재 synthetic 회귀는 OK·abstained=false로 실패** | `assembly.py`는 not-abstained+OK+value를 승격. ADR-006의 형식 review 구현은 별도 후속 | guard 자체가 없다는 옛 설명을 정정. 구현은 있으나 정규식 불일치로 부분 plate 오수용이 남음 |
| 3. 번호판 자체가 보이지 않음 | IncidentClip OCR 결과만으로 최종 REPORT_VIDEO의 plate visibility=false를 보증할 수 없음. no text/association 실패와 구분이 충분하지 않을 수 있음 | 최종 영상의 실제 false fact가 있으면 BLOCK. fact 미생산은 UNKNOWN | “없음을 관찰”과 “관찰하지 않음”이 다른 경로 |
| 4. Readout 실행 자체 실패 | `ReadoutRun.outcome=FAILED/PARTIAL`, failure 정보; PlateReadout 자체가 없을 수 있음 | 실패·재시도 notice + 사용 가능한 값 부재. 성공한 UNKNOWN으로 위장하면 안 됨 | 런타임 실패는 값 상태와 별도 보존 |

**정적으로 예상한 blocker / 실제 발생한 blocker:** #147 synthetic probe에서 plate를 제거하면 EVIDENCE `evidence.vehicle_number.present=UNKNOWN`, FINAL `package.report.content_length=UNKNOWN`, overall `UNKNOWN`이 됐고 builder는 우선 `package.requirement_not_ready`에서 멈췄다. ready report를 대입해 builder 자체를 격리하면 `package.input.vehicle_number_missing`, renderer에 빈 문자열을 주면 `vehicle_number must be a non-empty string`이 발생했다. 즉 “값은 UNKNOWN이지만 WARN Package”는 catalog 하나만 바꿔서는 성립하지 않고 builder·renderer 변경도 필요하다는 정적 판정이 확인됐다.

네 상태의 보존 정도도 실행으로 나뉘었다. 성공한 null UNKNOWN과 partial `NEEDS_REVIEW`는 plate 값을 Evidence로 승격하지 않지만 PlateReadout provenance는 남는다. partial 문자열을 `OK`로 표시하면 형식 검증 없이 그대로 승격됐다. abstain만 `PLATE_REREAD` Need를 만들었고, PlateReadout 자체가 없는 입력은 값도 Need도 만들지 않았다. 최종 영상 fact는 이와 독립적으로 true→PASS, false→BLOCK, 미관찰→UNKNOWN이었다. 다만 이 probe는 assembly의 소비 경계를 격리하기 위해 raw dict를 변형했다. `UNKNOWN+abstained=true` 등 조합 전체가 canonical Readout Producer의 유효 출력이라는 뜻이 아니며, PlateReadout 없음도 실제 실행 실패를 발생시킨 것이 아니라 **미실행/누락 입력 경계**만 확인한 것이다. 따라서 실제 infra 실패의 run outcome·notice 전달은 여전히 미확인이다. 현재 Evidence projection에서 “영역은 보이나 판독 실패”와 “PlateReadout 없음”이 값 부재로 수렴하므로 provenance/run/notice를 함께 소비해야 한다는 결론만 유지한다.

[Readout api][readout-code]와 [failure taxonomy][readout-failure]를 근거로 한 구분이다. “부분 판독이면 항상 `?`가 들어간다”는 계약은 없다. [#138 부분 판독 답변][i138-partial] 이후 **#138이 병합돼 taxonomy에 PARTIAL_PLATE_READ가 등재되고 해당 best_frame을 내보내지 않는 guard도 생겼다.** 따라서 taxonomy 공백·미병합이라는 옛 판단은 이 범위에서 해소한다.

**최신 구현 실측 — 정적 기대와 다름:** `742ca89`의 [추가 회귀][latest-target-test]는 `바5215`를 NEEDS_REVIEW·abstained=true·best_frame=null로 기대하지만 실제는 **OK·abstained=false·reason=null·best_frame 있음**이었다. [현재 `_abstain_reason()`][readout-code]의 raw regex `r"\\s+"`·`r"[가-힣]\\d{4}"`가 공백·숫자 클래스 대신 literal backslash를 매칭해 의도한 분기에 들어가지 않는다. 이것은 이미 명시된 partial 정책을 구현하는 **B: 버그 수정 후속**이며 UNKNOWN Package 허용 여부를 다시 결정할 이유가 아니다. 실제 영상의 부분 판독 빈도나 PLATE_IMAGE 생성까지 확인한 결과도 아니다.

9/27 Positive 4건은 네 실패 상태가 아니라 **plate OK** 사례다. 실제 프레임에서 `125호1108`을 확인했고 Evidence도 같은 Readout 값을 소비했다. 그러나 Readout association은 모두 LOW_CONFIDENCE/FALLBACK_ONLY인데 CaseView plate는 INFO_SOURCE_VERIFIED·needs_review=false였다. 판독 성공을 차량 연결 확정으로 확대하지 않는 검수 기준을 #139에 연결한다. 이 관찰이 UNKNOWN 허용 경계를 대신 결정하지 않는다.

#### 충돌과 최신 결정

**기존 결정 재검토 필요 — 방향 제시 완료, 계약 개정 미반영.** [9/25 Evidence/Product Owner 댓글][r146-plate]은 “번호판 식별 실패는 Package blocker가 아니라 경고가 있는 UNKNOWN 값으로 허용” 방향을 명시하고, 현재 UNKNOWN/BLOCK/필수 renderer의 후속 정렬을 예고했다. 따라서 “UNKNOWN 허용할까요?”를 월요일에 다시 묻지 않는다.

남은 것은 **허용 집합의 정확한 경계**다. 실제 판독 불가/영상 내 식별 불가를 허용하는 것과, 판독·최종 영상 검사를 실행하지 않았거나 실패한 상태를 같은 WARN으로 처리하는 것은 별도다. 특히 [ADR-005 I4][adr005]는 최종 REPORT_VIDEO 관찰 Producer가 아직 없어 mock_only라고 명시한다.

#### 제안안 — 참고

Owner가 제시한 방향을 반영하되 **미확보 plate 값은 null/부재로 보존하고, 사용자용 “읽을 수 없음”은 표시 계층에서 만든다**는 안을 제안한다. `"UNKNOWN"`을 실제 차량번호 문자열로 넣거나, 판독 결과만으로 plate visibility PASS를 생성하지 않는다.

| 변경 대상 | “plate UNKNOWN + WARN Package” 채택 시 필요한 정확한 후속 |
| --- | --- |
| ADR-002·ADR-005 | 기존 plate 부재 UNKNOWN / 최종 영상 식별 불가 BLOCK의 변경 범위와 사유를 **새 결정·supersede 관계**로 기록. 기존 Accepted 본문을 조용히 덮지 않음 |
| `contract-requirement-report-package.md` | `report_inputs.vehicle_number`의 nullable 등 정확한 wire type, missing/null 구분, ready 조건에서 허용하는 plate 사유·warnings 정의 |
| `contract-evidence-record-needs.md` | confirmed-only·부재 표현을 유지할 수 있음. 만약 “사용자가 판독 불가로 남기기로 함”을 저장하려면 값 수정과 다른 실제 action/provenance 경계를 확인. 자동 reread Need의 필수성·횟수도 정렬 |
| `requirement_rules_v4.json` 후속 revision | EVIDENCE plate 부재, FINAL plate visibility false, not-observed/infra 경로의 outcome를 **각각** 확정. 전체 UNKNOWN을 WARN으로 치환하지 않음. 기존 v2/v3/v4 보존 |
| `requirements.py` | plate None builder guard·`report_inputs` 생성, `package.report.content_length`의 template 선택·필수 slot 검사, 새 catalog와 package basis 정합성 |
| `policy.py`, `safety_report_policy_v1_1.json`, safety-report decision 문서 | plate 없는 specific/generic × location 있음/없음 조합을 지원하는 새 template/policy revision. 차량번호 없는 사실을 날조 없이 표현하고 content length도 같은 template로 평가 |
| Plate/Overlay·DerivedAsset 관찰 경계 | Readout의 UNKNOWN enum 신설은 불필요. 최종 REPORT_VIDEO 관찰 입력/Producer 문제는 I4에서 해결하거나, 해당 미관찰을 허용할 정책이면 명시적으로 결정 |
| Case `view.py`·CaseView 계약·Web | plate INFO_UNKNOWN 유지, package field state·warning·복사할 실제 값 없음 표현, 실행 실패 notice 별도. 가짜 사용자 확인 상태 금지 |
| tests·Mock·Eval | 네 plate 상황 × 최종 영상 true/false/미관찰 × 실제 응답 유무, nullable renderer·no-location 조합, 다른 BLOCK 유지, 오류/부분 문자열 오수용 회귀 추가 |

근거는 현재 plate 타입·builder·renderer의 세 중복 gate와 location-null 선례다. 이 변경으로 발생시각 UNKNOWN이나 report video 부재까지 자동 허용되는 것은 아니다. 제안은 참고이며 해당 Owner·Consumer 합의가 우선한다.

#### Owner 질문

**Q4 — Evidence/Product @flosure23, Readout @uminshin, Recording @cheol1203, Case @yuusoyeon:** 이미 제시된 UNKNOWN 허용을 계약화할 때, **실제 식별 실패와 최종 영상 fact 미생산/실행 실패의 outcome**를 어디서 구분할지 확인해 달라. nullable wire 표현과 무한 mandatory reread 방지도 같은 변경안에서 닫으면 된다. broad 허용 방향은 재질문하지 않는다.

#### 결정 상태

**D+B**, Q4의 미관찰/인프라 허용 경계만 **E 가능**. 현재 코드가 새 정책을 구현했다는 뜻은 아니다.

### D5. 다른 후보·시간 보정과 기존 값 무효화

#### #145 변경

F06·F08·F09·F13·F19. 새 후보는 새 초안이고 옛 값은 자동 승계하지 않는다. 그러나 현재 §9의 **“시간 보정으로 재탐색해도 번호판·신고 상황 유지 — 같은 차량, 같은 상황”**은 그대로다. 시간 이동 후 다른 차량을 고르는 경우까지 같은 차량이라고 보장하는 계약은 없다.

#### 현재 계약/ADR

[CorrectionRecord][correction-contract]의 selection context, [EvidenceRecord][evidence-contract]의 basis/provenance·supersedes, [Architecture §7-4][architecture]의 부분 재실행을 함께 적용해야 한다. 후보 변경은 `selection_rev`를 증가시키고 새 근거에 적용되지 않는 correction을 자동 사용하면 안 된다. `case_rev`는 사용자 의도/상태, `selection_rev`는 선택 context, timeline revision은 영상 시간축 버전으로 서로 다르다.

옛 Flow §9에는 **“번호판 유지, 이미 확인한 값 재확인 안 함 — case Owner 확인”**이 있었고 [PROTOTYPE-SPEC][prototype-spec] Ruling 5와 Prototype SELECT도 그 정책을 따른다. 이는 #145가 명시적으로 바꾼 기존 Product/Case 협의 내용이다. 다만 Final CorrectionRecord가 “후보 변경 때 번호판을 무조건 유지하라”고 정한 것은 아니다. **기존 유지 결정 재검토 필요**와 **이미 selection별 provenance를 지키는 계약**을 구분한다.

#### 현재 구현

- [Prototype machine][prototype-machine] SELECT(176 부근)는 occurredAt/clip/situation만 초기화하고 plate를 유지한다. SHIFT는 plate/situation을 유지하는 고정 mock 후보 전환이다.
- [Case domain][case-domain] reselect는 `selection_rev`만 증가시키며 현재 `EVIDENCE_REVIEW`에서만 허용한다. **READY 결과에서 OTHER_CANDIDATE는 거부**한다. Case correction wrapper가 별도로 case_rev를 올린다.
- [Evidence assembly][assembly]는 현재 selection_rev의 correction heads만 사용한다. 상황 응답의 candidate_ref도 검증한다. 원래 plate/시각 값이 새 candidate의 basis인지 확인하는 것은 view가 아니라 조립/호출 경계 책임이다.
- `regress_to_searching()`은 후보 목록을 지운다. 이는 #145의 “기존 후보·초안 보존”과 다르다(D9). 이전 `user_reviewed`를 새 draft 확인으로 재사용하지 않도록 하는 orchestration도 필요하다.

**정적으로 예상한 blocker / 실제 발생한 blocker:** #147 synthetic probe에서 READY의 후보 2개 중 다른 후보로 `correction.reselect_candidate()`를 호출하면 예상대로 `InvalidTransition`이 발생하고 선택·`selection_rev`는 유지됐다. 그러나 wrapper가 도메인 검증보다 먼저 `apply_correction()`을 호출하므로, 실패 뒤에도 `case_rev`가 3→4로 오르고 `OTHER_CANDIDATE` CorrectionRecord 1건이 남았다. “거부된다”는 정적 판정은 맞지만 **실패한 요청이 실제 사용자 정정 이력처럼 기록되는 부작용**은 새로 확인됐다. 별도 probe에서 READY `regress_to_searching()`은 stage를 SEARCHING으로 바꾸면서 후보 2개를 0개로 지우고 `selection_rev=1`은 유지했다.

**최신 영향:** domain/correction 구현은 `bae2818→742ca89`에서 변경되지 않았다. #73의 최신 완료 보고는 Recording 원본 무변형 범위이므로 Case의 후보 보존·실패 원자성·Q5 값 승계까지 닫지 않는다.

문서의 revision 설명에도 시차가 있다. 9/13 `case-selection-revision-persistence.md`는 후보 선택 시 case_rev도 함께 증가한다고 적지만, 9/14 domain 정정·현재 테스트와 #106 Case 답변은 **최초 선택은 selection_rev만 증가, 재선택 correction은 별도 case_rev 증가**로 설명한다. Tech Spec의 “빈 후보는 SEARCHING 유지”도 현재 domain의 9/14 정정(CANDIDATE_REVIEW로 전진)보다 오래된 설명이다. 새 정책을 물을 사안이 아니라 **C: 최신 Owner 설명·검증된 전이를 문서에 정렬할 항목**이다.

#### 값별 적용 경계

| 값 | 같은 후보에서 해당 값만 수정 | 다른 후보 선택 시 현재 근거에서 필요한 처리 |
| --- | --- | --- |
| 번호판 OCR | 새 readout/record가 이전을 supersede. 무관한 Search 유지 | 새 사건 구간으로 재판독; 옛 plate basis 자동 승계 금지 |
| 사용자 직접 입력 번호판 | 실제 correction으로 유지 | 이전 입력을 참고로 보여줄 수 있으나 새 selection의 CONFIRMED로 자동 적용하지 않음 |
| 발생시각 / EVENT_TIME_MANUAL | TimeResolution 재해석, stamp/report 요건 재계산; Search 유지 | 다른 사건시점으로 자동 이월할 수 없음. 새 selection의 시간 근거 필요 |
| TIME_HINT_EDIT / 조금 전·후 | Search 우선 범위 수정, 최종 발생시각 확정과 다름 | 새로 고른 후보가 같다는 근거가 없으면 번호판·상황 유지 특례를 적용하지 않음 |
| 사건 구간 | IncidentClip/Report Video·관련 요건 재생성 | 새 candidate span/basis로 생성 |
| 위치 | GPS/관찰/수정 등 provenance에 따른 값 보존 | 원래 위치 hint는 Case 입력으로 보관 가능; 새 사건의 확정 위치로 자동 승격하지 않음 |
| 위반 내용·신고 상황 | 실제 CORRECTED/USER_UNSURE provenance로 반영 | 새 event와 candidate_ref에 대한 응답 필요 여부는 D3; 옛 response 자동 복사 금지 |
| report type | 같은 사건이면 mapping/manual correction에 따라 text/requirements/package 재계산 | 새 event mapping 재평가. 이전 유형 수동 선택도 새 사건에 유효한지 별도 적용 |
| USER_REVIEWED | 필드 user_corrected와 별개 workflow | 옛 결과 확인을 새 draft 확인으로 사용하지 않는 경계 필요(D6) |

#### 충돌

**E:** Product의 기존 유지 협의 변경, 같은 차량 가정의 근거 부재. [#139 최신 경계][i139-final]는 현재 target-localization producer가 미정이라고 확인한다. 자유 문자열 track_ref를 동일 차량의 안정적 identity로 써서 옛 값을 복사하면 안 된다.

**B/D:** READY→새 draft 전이, 새 basis·selection_revision, 늦게 도착한 이전 작업 결과 배제, 새 command가 필요하다. 재선택 버튼을 잠가도 이미 실행 중인 옛 Job 결과의 revision 검증은 남는다.

#### 제안안 — 참고

| 안 | 장점 | 단점 | 영향 |
| --- | --- | --- | --- |
| A. 후보 변경 시 모든 후보 종속 값 비활성화, 원입력·과거 correction은 참고만 | #145·selection provenance와 가장 가까움; 다른 차량 혼입 예방 | 같은 차량이어도 재적용이 번거로움 | Case 새 basis/selection·Web 참고 표시, Evidence 현재 context 필터 |
| B. A + 사용자가 값별 “이 후보에도 적용”을 선택 | 직접 입력 재작업 감소, 새 사용자 provenance 확보 | 추가 UI·command와 field별 허용 범위 필요 | 새 selection에서 새 CorrectionRecord; 단순 옛 ref 복제 금지 |
| C. 동일 차량/사건 identity를 확인한 경우 자동 유지 | 반복 장면 탐색 효율 | 현재 신뢰 가능한 identity Producer 없음; 잘못된 승계가 조용함 | #139 이후 별도 association·정책·Eval 필요 |

**A를 기본안**, 재입력 부담이 관찰되면 B를 후속안으로 제안한다. C는 현재 구현 근거가 부족하다. “값 수정은 무관한 확정값 유지”와 “다른 후보는 새 context”를 함께 지키며, SHIFT 후 새 후보를 선택했다면 같은 기준을 적용한다. 제안은 참고이고 기존 협의 당사자의 판단이 우선한다.

#### Owner 질문

**Q5 — Case @yuusoyeon, Evidence/Product @flosure23, Web @uminshin:** 후보 변경의 기본안을 A로 두고, §9의 시간 보정 유지 특례를 **같은 selection context 안의 재탐색/값 수정에만** 한정할 수 있는가? 사용자 재적용 B를 이번 범위에 넣을 필요가 있는지만 함께 확인해 달라. 안정적 차량 identity를 Search가 이미 제공한다고 가정하지 않는다.

#### 결정 상태

**E+B/D.** 기존 유지 협의의 변경 확인 필요. 구현이 옛 Prototype을 따르는 사실 자체를 새 Flow의 오류로 판정하지 않는다.

### D6. “결과 화면”, `PACKAGE_READY`, `USER_REVIEWED`

#### #145 변경

F06·F12·F13·F16·F20. 불확실한 값도 결과에 보내고, 별도 “신고자료 만들기” 없이 handoff한다. 하지만 “결과”가 **부분 작업 결과인지 완성 ReportPackage인지** 구분되지 않는다.

#### 현재 계약/ADR

[CaseView §7·§10][caseview]의 `READY`는 **PACKAGE_READY가 성립한 시점**이다. `EVIDENCE_SUFFICIENT`, `PACKAGE_READY`, `USER_REVIEWED`는 세 별개 gate다. [ReportPackage][package-contract]는 ready-only immutable object이며 incomplete draft 계약이 아니다. `evidence=null`은 “확정 Evidence 조립 전”, `evidence.plate_display.value=null`은 “조립된 Evidence에서 plate 값 부재”로 다르다.

#### 현재 구현·상태 전이표

| 상태 / 자료 | 현재 Web 선택 | gate 의미 | #145에 대응하려면 |
| --- | --- | --- | --- |
| INTAKE / SEARCHING | PROGRESS | Package 없음 | 입력 홈/분석 진행 분리는 UI 구현 |
| CANDIDATE_REVIEW, 후보 0 | NO_RESULT | 정상 빈 결과 | 유지. 실패·미관찰과 구분 |
| CANDIDATE_REVIEW, 후보 있음 | CANDIDATES | 명시 선택 대기 | Case 자동 선택으로 일반 happy 경로에서 빠르게 통과; optional compare는 결과 출구 |
| EVIDENCE_REVIEW, evidence=null | **PROGRESS** | Evidence 조립 전. 작업이 없더라도 현재 선택 함수는 PROGRESS | UNCERTAIN 응답 대기·NOT_OBSERVED 결과가 영구 진행처럼 보이지 않을 표현 필요 |
| EVIDENCE_REVIEW, evidence 있음, 요건 미충족 | EVIDENCE | 부분 값은 표현 가능. package=null | “결과 검토” UI로 사용할 수 있으나 신고문·영상 초안이 자동 생기지는 않음 |
| EVIDENCE_REVIEW, EVIDENCE PASS/WARN | EVIDENCE | EVIDENCE_SUFFICIENT만 성립, FINAL gate와 별개 | 자료 생성·최종 요건 검사 진행 표시 |
| READY + FINAL PASS/WARN + package | HANDOFF | PACKAGE_READY. user_reviewed는 별개 | 준비된 결과·경고·최종 사용자 행동 표현 |
| READY + package=null | 방어적으로 EVIDENCE | **정상 계약 상태가 아님** | 이 fallback을 incomplete draft 지원 근거로 쓰지 않음 |
| 어느 stage든 user_reviewed=true | 별도 표시 | 계약상 READY 이전에도 가능 | 새 결과 확인과 어느 revision을 확인했는지 Case workflow 정렬 필요 |
| READY에서 다른 후보 선택 | 현 domain에서 거부 | 현 OTHER_CANDIDATE는 EVIDENCE_REVIEW 전용 | 새 selection/draft 전이와 이전 결과 격리(D5) |

근거: [selectScreen.ts 41–70][select-screen], [EvidenceScreen][evidence-screen], [HandoffScreen][handoff-screen], [Case domain][case-domain]. EvidenceScreen은 6개 값·상태를 보여주지만 Package 전 영상/신고문 draft·편집 command를 제공하는 완성 결과 화면은 아니다. Handoff 버튼 표시와 실제 다운로드/복사/command 연결도 별개다.

**정적으로 예상한 blocker / 실제 발생한 blocker:** OBSERVED + 무응답 synthetic 실행은 Evidence와 EVIDENCE PASS까지 진행했지만 FINAL UNKNOWN과 `PackageNotReady`에서 멈췄다. [#147 Positive 기록][pr147-positive]은 실제 Fine/OCR 뒤 `report_package=null`인데도 dump script가 `case.mark_ready()`를 먼저 호출해 `CaseView.stage=READY`를 출력한다. 승인 후 같은 영상 1회 재실행은 Fine `NOT_OBSERVED`로 정상 비조립됐고 evidence/package가 모두 null이었지만 역시 `stage=READY`였다. 따라서 이 문제는 Positive 부분 결과에만 한정되지 않고, **음성 종료까지 READY로 투영하는 공통 전이 우회**다. 두 실행 모두 현재 CaseView 계약의 PACKAGE_READY를 만족한 증거가 아니다. #147이 progress를 PENDING으로 보이게 한 수정과 별개로, READY 전이 조건 자체가 실행 경로에서 우회되고 있다.

**최신 영향:** #147의 progress override 제거와 occurred_at null 방어는 현재 develop에 있으며 `test_progress_ready_without_package.py`도 PASS다. 이는 표시 수정의 증거다. [현재 dump][latest-dump]의 `case.mark_ready()`가 Package 결과보다 앞서는 전이는 남아 있어 D6의 의미 충돌은 해소되지 않았다. Web은 Package 없음을 방어하지만 §3의 count 실패 때문에 해당 선택 loop 전체의 최신 회귀 PASS를 주장하지 않는다.

9/27 추가 5건도 모두 READY였지만 Package는 없었다. Positive 4건은 `package_assembly=PENDING`, running_jobs=[]여서 이 snapshot만으로 실제 작업이 진행 중이라고 볼 수도 없다. 값의 UNKNOWN을 보존한 것은 정합하나 stage·진행 상태·허용 action을 일관되게 표현하는 문제는 별개다. CaseView 출력까지 검수했으며 이번에 브라우저 조작·handoff command를 실행한 것은 아니다.

#### 충돌

**기존 결정 재검토 필요:** READY를 “뭔가 보여줄 결과가 있음”으로 바꾸거나 ReportPackage에 미완성 값을 넣으면 Final gate/ready-only 결정이 바뀐다. UI 화면 이름 변경만으로 해결되지 않는다.

또한 #145의 “모든 값이 불확실해도 결과”는 **모든 UNKNOWN으로 Package 발행**과 같지 않다. 시각이 없으면 TimeResolution은 resolved 없음, `report_inputs.occurred_at`은 필수이며 최종 time rule도 UNKNOWN이다. report video 미생성·규격 BLOCK 역시 그대로다. 위치 null 선례를 이 전체에 일반화하지 않는다.

#### 제안안 — 참고

**UI의 결과 검토와 Package readiness를 분리**하는 안을 제안한다. `READY`/ReportPackage의 의미는 유지하고, CaseView에 부분 결과·대기 사유·허용 action을 안전하게 표현한다. 값만 먼저 보여주고 아직 없는 영상·신고문은 준비 전으로 표시할 수도 있다. 실제 draft 텍스트/미완성 영상을 제공하려면 별도 projection과 artifact basis를 명시하고 ReportPackage로 위장하지 않는다.

최종 사용자가 handoff를 요청할 때 실제 검토 intent를 기록하는 방안이 자연스럽지만, **링크 클릭만으로 개별 필드 CONFIRMED나 situation_response를 생성하지 않는다.** #106의 USER_REVIEWED command 범위에서 연결한다. 영향: CaseView·Case workflow·Web result composition·Eval. Evidence ready-only 유지 여부는 D3의 선택에 달려 있다. Owner 판단이 우선한다.

#### Owner 질문

**Q6 — Case @yuusoyeon, Evidence/Product @flosure23, Web @uminshin, Wireframe @kim1034:** 결과 화면을 Package 이전에도 보여주는 검토 화면으로 정의하고, ready-only Package와 별도 projection을 유지할 수 있는가? 보여줄 최소 자료(값만 / draft 텍스트 / 미완성 영상)와 실제 최종 검토 intent의 기록 시점을 정해 달라. D3 Q3과 한 묶음으로 답하면 된다.

#### 결정 상태

**D/E.** 세 gate를 합치지 않는 것은 현재 Accepted 결정. 화면 결과의 최소 보장은 Product/Consumer 합의 필요.

### D7. 위치 UNKNOWN

#### #145 변경

F08·F12의 불확실한 위치도 결과로 넘기는 방향. 위치 부재를 Package blocker로 새로 만들지 않는다.

#### 현재 계약/ADR

[ADR-003][adr003]·[#48 최종 Owner 결정][i48-final]이 **명시적 `location:null`, FINAL_PACKAGE WARN, 위치 없는 template**를 채택했다. EVIDENCE 위치 WARN은 더 이른 ADR-002부터 존재한다. `search_keyword` 없음 notice는 location null 자체와 같은 조건이 아니다.

#### 현재 구현

`requirements.py`, `policy.py`의 no-location template, `view.py` field state와 위치 미확보 notice, Web INFO_UNKNOWN/WARN 표시가 존재한다. 관련 테스트를 이번에 통과했다. [#86 최종 댓글][i86-final]은 P/R 공용 fixture·CaseView·checklist의 active catalog 동기화가 끝났음을 명시한다. 최초 본문의 “어느 쪽이 정본인가” 질문은 철회된 질문이다.

**최신 영향:** #119에서 [Web의 `notice.location_search_keyword_missing` 문구][latest-web-labels]와 fallback 방지 회귀가 추가돼 PASS다. 발동 조건은 `location=null` 자체가 아니라 검색어 부재다. 현재 필요한 후속은 실제 notice 발행·표현 연결의 검증이며, 위치-null Package 정책은 재논의하지 않는다.

#### 충돌

**A:** Product와 현재 정책·구현 정합. 위치 없는 WARN Package는 유지한다. **C:** Wireframe 고정 위치·전체 완료 표시에 빈 값의 설명이 빠지면 UI만 동기화한다. 새 위치 추정값을 만들어 채우지 않는다.

#### 제안안 — 참고

현 계약을 그대로 사용하고, null 위치와 선택적 검색 키워드·외부 직접 선택 안내를 구분해서 표시하는 안을 제안한다. 근거는 ADR-003과 완료된 #86이다. 영향은 필요한 Web/Wireframe 문구 동기화뿐이며 Owner 판단이 우선한다.

#### Owner 질문

**없음 — 재논의 불필요.**

#### 결정 상태

**A, 일부 C.** #48이 열려 있다는 이유만으로 위치 정책이 미결이라고 표시하지 않는다.

### D8. Web / Wireframe / Prototype 전수 대조

#### #145 변경

F02~F08·F10~F14·F18. 3단계·결과 우선·optional 비교·중간 plate 승인 제거·별도 자료 생성 CTA 제거.

#### 현재 계약/ADR

[Web value-state-display][web-display]는 CaseView를 정본으로 소비하고 readiness를 재판정하지 않는다. [#106 최신 댓글][i106-final]은 공통 command 입력 `case_id / expected_case_rev / kind / payload`, 성공 후 새 CaseView 또는 조회 가능한 revision, 실패 유형 전달을 정리했다. 후보 선택 command는 이제 **결과 재선택**용이며, Web local state만 바꾸거나 직접 Readout/Evidence를 호출하지 않는다.

`notices.actions`의 현재 7종은 JOB 3개와 LOCAL 4개다. 후보 선택·상황 응답·USER_REVIEWED가 자동으로 이 enum의 새 값이 되는 것은 아니다. #106에서 action/command 경계를 마무리한다. [#123 최신 댓글][i123-final]은 StreamScreen 안에 후보 선택 entry를 합치려던 초기 전제를 철회했다. 진행/결과 분리와 optional compare가 현재 범위다.

**최신 영향:** #123은 9/27 **closed**이며 남은 작업을 #122/#106·개별 Web 변경으로 넘겼다. #119는 notice mapping만 바꿨고 Wireframe/Prototype·selectScreen·command surface에는 이번 diff상 변화가 없다. 따라서 14장 stale 매트릭스는 유지하되 닫힌 #123을 구현 대기 이슈로 다시 쓰지 않는다. #146의 최종 승인 댓글은 다음 단계를 실제 사용자 동선/API·DB·queue/worker E2E로 제안한다([최종 review][r146-final]); 기존 Contract gate가 변경됐다는 수락은 아니다.

최종 재조회에서 추가된 [#146 9/25 14:57 UTC Web 답변][r146-progress]도 반영했다. 사건 찾기와 자료 준비의 **두 진행 화면**, ETA/퍼센트 미제공은 Flow와 정합한다. “분석 중 polling으로 시작하고 이후 SSE 검토”는 Owner가 제시한 구현 방향이며 Final 전송 계약으로 수락됐다고 단정하지 않는다. 재연결 시 현재 CaseView를 다시 읽는 것과 사용자 command는 분리한다. 경과시간에 사용할 authoritative 시작 시각/조회 경로도 실제 연결 시 확인할 후속이며, 이 umbrella에서 WebSocket/SSE 선택을 새 Product Decision으로 올리지 않는다.

#### 현재 구현·이미지별 판정

아래는 README 이름만 읽은 결과가 아니라 **PNG 자체를 연 결과**다. 이미지들은 과거 시점 snapshot이므로 증거 파일을 수정·폐기하자는 뜻은 아니다. 후속 시안과 README에서 현재 기준을 구분한다.

| 화면 / 실제 잔존 내용 | 분류 | 후속 처리 |
| --- | --- | --- |
| `00-flow.png`: 7단계, AI 이해 확인, 명시 후보·plate/상황 확인, 자료 만들기 | **새 Flow에 맞춰 수정** | 3단계 흐름으로 재정리. 결과 gate 상세는 D3/D6 대기 |
| `01-home.png`: 별도 새 신고 진입, 최근 신고 카드 | **새 Flow에 맞춰 수정** | 업로드+설명 홈으로 통합. “제출 완료”는 외부 제출 사실을 실제로 아는지 별도 근거 없이 보장하지 않음 |
| `02-my-record.png`: 제출한 신고 진행상황 확인·제출 상태 | **Product Decision 대기** | #145 기본 경로/후보 결과 이력 Deferred와 구분. 실제 외부 신고 추적 연동으로 오인될 표현은 scope 정리 전 완료 기능으로 약속하지 않음 |
| `03-upload.png`: 업로드+기억 입력, 옛 상단 단계 | 내용 **그대로 유지**, 단계 **수정** | 입력 내용 보존, 3단계 반영 |
| `04-upload-ing.png`: 업로드 수, AI가 이해한 내용 편집·찾아보기 | 업로드 **유지**, 승인 **제거** | 업로드 byte/file 진행과 AI 분석 ETA는 다름. 사실 고지는 유지 |
| `05-upload-done.png`: 완료 파일명과 달리 이미지에는 업로드 중/41·42 등의 진행 문구 잔존 | **새 Flow에 맞춰 수정** | 실제 완료/부분 완료를 authoritative 상태로 구분 |
| `06-upload-fail.png`: 실패 색상과 진행 문구 혼재 | **새 Flow에 맞춰 수정** | 일부 파일 실패만으로 전체 분석 실패가 되지 않도록 성공 입력·skip·재시도 안내 |
| `07-main-flow.png`: 중간 조건 수정·후보 개입·번호판에서 멈춤, 번호판 확인 후 자료 만들기 | 승인 gate **제거**, 결과 이동 **수정**, 보장 문구 **대기** | “창 닫아도 계속”은 실제 background/runtime 보장 확인 필요. 모든 자료 준비 완료와 plate만 미확정 상황을 혼동하지 않음 |
| `08-candidates.png`: 1번 진행 중, 카드별 아니에요, 단서 ✓/✗ | **새 Flow에 맞춰 수정** | 결과의 optional 비교로 이동. 카드별 reject 목록은 #106에서 미채택; 상류 fact 없는 ✓/✗ 제거 |
| `09-compare.png`: 두 후보 비교·현재 1등·단서 일치 표시 | 비교 **유지**, 판단 문구 **수정** | rank와 카드/시간축 번호 일치. 원문·관찰 문장 병치. “이 사건 맞아요”는 새 초안 요청과 실제 상황 응답을 구분 |
| `10-evidence.png`: 원본·출처 병치, 이전 진행으로 돌아감, 시각 source 전환 | 근거 **유지**, 동선 **수정**, command **대기** | 결과에서 열고 결과로 복귀. source 선택을 Web의 time priority 계산으로 구현하지 않음 |
| `11-plate.png`: 확대·문맥 frame·직접 입력·확정 | 편집 기능 **유지**, 중간 필수 정지 **제거** | 결과 안의 선택적 plate 편집. MVP 단일 best-frame/preview와 다중 frame Should를 #47대로 구분 |
| `12-no-result.png`: 모두 확인 문구, 범위/조건 변경 | 출구 **유지**, 범위 문구 **수정** | 실제 scope coverage 없이 “12개 모두 확인”을 고정 표시하지 않음. 새 탐색 경계 D9 |
| `13-handoff.png`: 옛 단계, 복사/다운로드/외부 이동 | 동작 방향 **유지**, 상태·문구 **수정** | 새 3단계·실제 field state·warnings. UNKNOWN plate는 복사할 실제 값이 없음을 표현. 클릭 구현과 외부 실제 제출은 별도 |

#### Prototype와 Web 코드의 차이

| 코드 | 판정과 영향 |
| --- | --- |
| Prototype `Upload/Describe/Scope` 화면·machine의 START_SEARCH | **C/B**: 별도 설명/사전 이해 수정 동선을 새 홈·자동 구조화로 동기화 |
| Prototype `CandidatesScreen`, SELECT·ACCEPT·SHIFT | **C/B**: 초기 명시 후보 선택→자동 선택 결과. SELECT의 plate 보존은 D5 결정 후 변경 |
| Prototype `PrepareScreen` 및 machine review gate | **C/E**: plate가 needs-review가 아니고 situation이 user-confirmed여야 통과. 중간 gate 제거는 D3의 실제 응답 정책과 정렬 |
| Prototype `ReviewScreen`/reportBody 및 mock | **C/B**: 자료 만들기·고정 확인 상태·mock 신고문은 새 runtime Package 보장 근거 아님 |
| Web `selectScreen` | **D/B**: rank1 선택 주체는 Case. evidence=null 대기/부분 결과 표현은 D6 결정 후 갱신 |
| Web `CandidatesScreen`/`CandidateCard` | **B/D**: rank·uncertainties가 계약에 없으면 추측하지 않음. command는 #106 연결 |
| Web `EvidenceScreen` | **B/D**: 현재 값 표시 화면. 새 통합 결과의 영상·draft·편집 기능 미완성 |
| Web `HandoffScreen` | **B**: 경고·field state 소비는 존재. 복사/다운로드/외부 이동 버튼의 표시가 command/실제 수행 완료를 뜻하지 않음 |
| Web `DisplayRow` / value-state 규칙 | **A**: UNKNOWN/null과 출처 보존. 모든 AI 결과를 강제로 INFO_AI_ESTIMATED로 바꾸지 않음 |
| PROTOTYPE-SPEC·Wireframe README·Case 옛 Tech Spec 설명 | **C**: 현재 흐름 설명과 과거 snapshot·완료 증빙을 분리. 역사 기록은 최신 문서 링크로 안내 |

#### 충돌

화면 stale만으로 Product Decision을 늘리지 않는다. #122의 projection, #106의 command, D3/D5/D6의 정책이 정해지면 대부분 문서·구현 동기화다. [#146 Web Owner 최신 답변][r146-wire]도 Wireframe이 #145보다 이른 시안임을 확인한다. #146 본문의 “새 Flow에 맞춘 Wireframe”은 이 후속 답변과 이미지 증거로 범위를 좁혀 해석했다.

#### 제안안 — 참고

3단계 상위 흐름과 결과의 optional editor/compare를 먼저 정리하고, D3/D6의 미결 gate에는 확정 CTA 문구를 넣지 않는 안을 제안한다. `신고자료 만들기` 삭제가 사용자 최종 승인·실제 상황 응답까지 자동 처리한다는 뜻은 아니다. 영향: Wireframe/Prototype/Web, #106/#122 Consumer 테스트. Owner 판단이 우선한다.

#### Owner 질문

별도 UX 정책 질문을 추가하지 않는다. Web @uminshin·Wireframe @kim1034는 **Q1/Q3/Q5/Q6의 답을 반영할 화면 범위**를 확인한다. 외부 신고 추적 화면은 기존 범위 확인으로 분리하고 기본 Flow 회의 안건에 넣지 않는다.

#### 결정 상태

주로 **C/B**, 미결 정책에 종속된 부분만 **D/E 대기**. #123 초기 StreamScreen 합의 요청은 재개하지 않는다.

### D9. 재탐색·취소·timeout·부분 재실행과 결과 보존

#### #145 변경

F06·F07·F11·F17·F19. 조건 수정/시간 보정/전체 거절은 새 탐색 의도이며 기존 후보·초안을 보존한다. 중단/timeout/infra는 같은 여정의 결과다. 남은 범위를 이어서 탐색하되 진행 중에는 사용자에게 내부 계획 승인을 요구하지 않는다.

#### 현재 계약/ADR

[JobExecution v1.1][jobexec]은 CANCELLED와 partial produced 보존을 이미 허용한다. [resume identity 결정][resume]은 사용자 “이어서 찾기”도 **새 job_id**, 자동 infra retry만 같은 job_id·새 attempt로 정했다. CaseView는 CANCELLED를 PARTIAL로 투영하고 중단 이유는 notice로 표시한다. **resume identity는 미결이 아니다.**

[Architecture §7-4][architecture]는 번호판 직접 수정→Evidence/요건, plate reread→Readout, time manual→TimeResolution/stamp, report type→정책/신고문, span→영상/관련 요건 등 부분 재실행을 구분한다. [CorrectionRecord][correction-contract]는 새 수정과 이전 record의 supersede를 보존한다.

#### 현재 구현

`jobs.py`·취소/infra mock은 새 job·attempt·PARTIAL을 검증한다. 반면 domain `regress_to_searching()`은 candidates를 비워 #145의 보존 요구와 다르며, complete draft와 active draft의 분리도 없다. 모든 값 수정에 Search 전체를 재실행할 필요는 없다.

[#72][i72]는 timeout 실제 숫자·확장 정책을 다룬 기존 이슈다. [#149 최신 Search 답변][i149-latest]은 scope budget과 factory 60초 deadline의 이중 제한을 지적한다. **[#152][pr152]는 병합됐고** Coarse/Fine request의 deadline을 provider retry까지 넘기는 [회귀][latest-deadline-test]가 이번에 통과했다. 재시도 budget 준수는 구현됨으로 갱신하되 factory budget 단일화까지 완료했다고 읽지 않는다. 자동 scope 확대 권한(Q7)과도 별개다. [#73 Recording 최신 댓글][i73-latest]의 원본 무변형 검증 완료를 기존 후보/초안 보존 구현까지 완료한 것으로 확대하지 않는다.

#### 충돌

| 변경·실패 | 보존/재실행 기준 | 분류 |
| --- | --- | --- |
| 사용자 중단 / timeout / infra failure | 성공한 부분 결과·원본·과거 run 보존, 현재 작업 상태/다음 action 표시 | **A/B**. 이미 있는 계약의 실제 연결 |
| 새 범위·시간 hint·전체 거절 | 새 scope/intent, 이전 후보·초안은 과거 기준임을 표시하고 보존; active basis와 분리 | **B/D**, #73 연계 |
| 값만 수정 | 해당 downstream만 다시 계산; Search 전체 재실행 아님 | **A/B**, 기존 부분 재실행 표를 유지 |
| 남은 범위 자동 확대 | Flow §6은 이어서 확인, §22는 범위가 넓어짐·추가 시간/비용을 먼저 안내. 범위/예산 초과 권한은 계약으로 자동 부여되지 않음 | **E**, 문구와 실행 경계 정렬 |
| 진행 중 조건 수정 | §7의 출구와 §6의 “내부 계획 수정 없음”을 구분해야 함 | **C** 우선: 새 사용자 hint intent인지 내부 AI plan 편집인지 명시 |
| ETA | 새 §19는 미제공, §22의 “약 4분” 예시는 남음 | **C**: 실측 없는 고정 ETA 약속 정리 |

#### 제안안 — 참고

**처음 위임한 범위·budget 안의 후속 탐색은 자동, 이를 넘는 확대는 새 사용자 탐색 intent**로 구분하는 안을 제안한다. 전체 승인 화면을 복원하지 않으면서 기존 비용 경계를 지킬 수 있다. 이전 후보는 지우지 않되 새 결과와 혼합 정렬하거나 옛 Package로 현재 handoff하지 않는다. 기존 영상·immutable run 보존은 result history UI를 구현하는 것과 다르다.

영향: Case scope/활성 결과 집합·projection, Search budget 전달, runtime deadline·Usage, Web 복구, Eval 부분 결과·late completion 테스트. 실제 숫자는 #72/#149 실측 논의가 우선한다. 제안은 참고이고 Owner 합의가 우선한다.

#### Owner 질문

**Q7 — Case @yuusoyeon, Product @flosure23, Search @kong2488-star:** §6 자동 후속 탐색을 **이미 위임한 scope/budget 안**으로 해석하고, 범위·budget 확대는 기존 §22의 새 사용자 intent로 분리할 수 있는가? timeout 숫자·factory cap은 #72/#149에서 답하고 umbrella에서 다시 설계하지 않는다.

#### 결정 상태

**A/B/C/D**, Q7만 **E**. #73의 보존 구현과 #72/#149/#152의 실행 제한 후속을 연결한다.

### D10. IncidentClip·Report Video·plate image·시간과 실제 handoff

#### #145 변경

F08·F10~F13. 사용자 결과에서 신고용 영상을 주로 보여주며, 별도 자료 만들기 클릭 없이 자동 준비한다. 후보 변경 뒤 plate와 overlay를 병행 재판독한다.

#### 현재 계약/ADR

[Recording/DerivedAsset][asset-contract]에서 IncidentClip은 판독 입력이고 Report Video는 제출용 파생 자산이다. 사용자 화면에서 IncidentClip을 따로 안 보여준다고 내부 자산을 제거하지 않는다. [TimeResolution §12][time-contract]는 확정 Evidence 이후 Report Video에만 사후 timestamp 표시를 허용하며 원본/IncidentClip에 삽입하고 재OCR하는 순환 근거를 금지한다.

[#47 최신 Recording 답변][i47-final]은 plate image 입력을 **best_frame.frame_ref + plate_bbox_xywh**, 원본 픽셀 좌표의 문맥 포함 단일 이미지로 정리했다. 생성은 최종 package/report-video 준비 시점이며 사용자 plate confirmation이 선행 조건이 아니다. [Readout §best_frame][readout-contract]은 이를 표현할 계약을 갖췄다. 다중 frame preview는 기본 MVP 필수로 다시 묻지 않는다.

#### 현재 구현

- Recording에 실제 IncidentClip/frame/span/AssetFacts 경로가 있다. **#138의 [RecordingFrameSource][latest-paddle]가 이제 develop에 존재**하며 공개 capability와 canonical FrameRef를 보존하는 단위 회귀도 PASS다. 그러나 [현재 Case][real-e2e]는 여전히 `LocalVideoFrameSource({clip_ref: 원본 경로})`를 사용한다. 따라서 “adapter 미구현”에서 **“구현된 adapter로 Case 배선 교체 필요”**로 후속 범위를 좁힌다. 고정 30/50/70%의 sampling 양은 여전히 Readout Owner 후속이며 전체 clip 정밀 탐색이 완료된 것은 아니다.
- Case가 `best_frame`으로 plate preview를 투영하거나 실제 PLATE_IMAGE export를 발주하는 경로는 미완성이다. `evidence.preview_ref`는 기존 사건 thumbnail이며 plate preview로 재정의하면 안 된다(#47의 정정·후속 댓글).
- **PlateReadout 발행 상수 v1.2→v1.3은 #138에서 수정됐고 현재 public 함수 회귀가 PASS다.** 다만 `data/mock/readout`의 active fixture 4개 파일·5개 객체에는 v1.2가 남아 있다. 런타임 수정과 fixture/계약 헤더 검증 후속을 분리한다. Overlay v1.2와 과거 실험 snapshot은 정상 이력이므로 일괄 갱신 대상이 아니다. [#146 version 답변][r146-version]의 후속 전체가 끝났다고 표시하지 않는다.
- ReportVideo Job intent·Mock artifact는 있으나 실제 최종 영상 생성과 I4 관찰을 포함한 Positive **Package** E2E 증빙은 없다. 최초 `bae2818`에는 없었던 [#147 Positive 실행 기록][pr147-positive]은 **현재 develop에 병합**됐다. 실제 Fine `OBSERVED`→PaddleOCR `125호1108`→Evidence→CaseView/Web 증거가 존재하므로 “현재 Positive 증빙 없음”이라고 쓰지 않는다. 이 기록과 본 조사 `032efc0` 실측 모두 Package는 BLOCKED였으며, 최신 develop 유료 재실행·handoff 증거는 아니다.
- [ADR-005 §5.7][adr005]의 I4는 최종 REPORT_VIDEO 번호판/시각 관찰 Producer 입력 계약부터 미연결이다. IncidentClip의 plate OCR, export byte_size, transform provenance는 각각 다른 사실이다. “각인 적용됨”만 recording transform으로 증명 가능하고, 영상 내 실제 가시성과 같지 않다.
- [#159 Recording baseline][latest-recording-baseline]은 실제 입력 1개·3회, 분석 범위 0–20.024656초/incident 1–2초에서 전체 중앙값 9.3125912초를 기록했다. 이는 별도 Python/ffmpeg 환경의 **Recording 처리만** 측정한 기존 Owner 증거다. source→analysis/incident/frame capability와 원본 불변 근거를 보강하지만, 이 보고서의 Search/OCR latency에 합산하거나 완성 Package 성능으로 인용하지 않는다. export는 해당 실험 범위 밖이다.

**정적으로 예상한 blocker / 실제 발생한 blocker:** 9/26 1회는 음성으로 downstream을 실행하지 않았다. **9/27에는 Positive 4건에서 IncidentClip/OCR/Evidence 이후의 자산 blocker도 확인**했다. FINAL의 report_video.exists·plate_visible_in_report_video·attachment count/total size가 UNKNOWN이고, basis.asset_refs=[]였다. source_asset facts만 공급하는 [#147 배선][pr147-real-e2e]과 일치한다. 시간과 상황 응답을 채워도 제출용 자산 생성·등록과 I4 관찰을 함께 해결하기 전에는 ready-only Package 완료를 보장할 수 없다. size 검사 2개의 PASS를 실제 파일 존재·검증 성공으로 오독하지 않는다.

R3의 best frame은 3.873초인데 candidate end는 3.800초다. [LocalVideoFrameSource][pr147-paddle]가 clip_ref에 연결된 **원본 영상**을 30/50/70%에서 읽는 기존 단순화가 실제 후보 경계를 벗어났다. 따라서 이번 OCR 성공은 진짜 픽셀 판독 근거지만 `candidate 범위 → canonical frame → best frame/PLATE_IMAGE` 배선 완료 증거는 아니다. 기존 #47/#139 및 Case/Readout clip 배선 후속에서 원본/clip offset·frame_ref 정합성을 검수해야 한다는 참고안을 제시한다.

#### 충돌

**B/D:** plate preview field·export capability와 최종 영상 관찰 입력은 기존 후속 항목이다. #145가 이들을 새 정책으로 만들지는 않았지만 자동 결과 완료를 약속하려면 연결해야 한다. **E는 D4/D6로 제한:** 최종 영상 사실이 없어도 handoff를 허용할지 여부는 기존 gate를 바꾸므로 별도 결정이 필요하다.

발생시각 UNKNOWN의 Package 허용은 결정돼 있지 않다. Filename/metadata fallback은 값이 있어도 NEEDS_REVIEW이고, verified overlay/실제 수동 확정만 OK라는 Accepted 우선순위를 유지한다. Web이 filename과 overlay 중 직접 “더 맞는 것”을 고르는 계산을 하지 않는다.

#### 제안안 — 참고

기존 #47·I4를 완료 의존성으로 링크하고, **판독 관찰→시간/증거 확정→제출용 영상 생성→실제 자산 사실/필요한 관찰→최종 요건→Package** 순서를 유지하는 안을 제안한다. 독립 plate/overlay 병행은 가능하지만 전체 파이프라인의 무조건 병렬화를 뜻하지 않는다.

근거는 원본 보존·post_stamp·ready-only 계약이다. 영향: Recording capability, Readout 입력/관찰, Case 발주·projection, Evidence 요건, Web preview, Eval 실제 asset 검증. 단일 best-frame 결정이나 좌표계는 재논의하지 않으며 Owner 합의가 우선한다.

#### Owner 질문

독립 새 질문 없음. Recording @cheol1203·Readout @uminshin·Case @yuusoyeon은 **#47의 capability/preview와 I4 Producer 접합**을 기존 논의에서 닫는다. Q4가 관찰 미실행까지 허용할 경우에만 그 영향 범위를 이 항목에 반영한다.

#### 결정 상태

**A+B/D**, 기존 이슈 연결. #139의 target-localization Owner/호출 위치 결정도 #122 자동 후보 선택과 분리한다.

### D11. 로그·revision·결과 history와 재사용

#### #145 변경

F06·F15·F19. 원문·수정 출처·이전 결과를 보존하지만, 사용자용 후보 결과 이력·즉시 재사용·연속 선택은 기본 범위에서 제외한다. 자동 초안 시작과 사용자 재탐색 행동을 기록한다.

#### 현재 계약/ADR

CandidateEvent/AnalysisRun, ReadoutRun, EvidenceRecord, TimeResolution, ReportPackage는 immutable 실행·근거 이력을 보존한다. CorrectionRecord는 실제 사용자 수정이며 자동 rank1 선택을 사용자의 사건 확정 correction으로 생성하지 않는다. [JobRecord A절 §7][caseview]의 동일 input fingerprint 성공 결과 캐시는 runtime 실행 정책이다. §27의 사용자용 결과 재사용 UI Deferred를 이 캐시 금지로 해석하지 않는다.

[#74 PM 최종 댓글][i74-final]은 평가 재사용/학습 재사용 구분과 익명화·동의 방향을 채택하되 persistence/gating/철회·삭제 구현을 외부 데이터·데모 준비 시점까지 **의도적으로 Deferred**했다. 옛 correction-log-reuse 문서와 W7 baseline의 “5건 미결/PM 승인 대기”는 이후 댓글을 반영하지 못했다.

#### 현재 구현

`correction_log.py`는 익명화 export와 selection_rev/supersede 정보를 보존한다. 원입력→최초 추출→수정→최종값 완전 재현은 D1의 raw intake 배선이 필요하다. domain의 단일 후보 배열은 과거 draft와 active result를 분리하는 UI history 모델을 제공하지 않는다.

승인 후 실행 wrapper가 provider 응답에서 Coarse 998 token, Fine 3,466 token을 계측했지만, 반환된 Fine `AnalysisRun.usage_summary`는 `processed_duration_ms=5533`, `latency_ms=13828`만 갖고 `token_usage=null`, `total_cost=null`이었다. #147 `fine.py`가 이 두 값을 명시적으로 null로 구성한다. 계약상 nullable이므로 schema 위반으로 단정하지 않지만, 실제 호출량이 공개 run projection에서 사라지는 **관측성 공백**이다. 단가 미설정으로 비용도 측정할 수 없었으며 null을 0원으로 해석하지 않는다. provider/Usage/pricing 경계는 새 정책 이슈를 만들지 않고 기존 #153에 이 실측을 연결한다.

9/27 추가 5건에서도 같은 Fine token/cost null을 확인했다. 계측 실패의 실제 Coarse 요청 5회까지 합쳐 이날 15회·20,710 token을 기록했으며, 오류가 난 run의 이미 소모된 usage를 누락하면 집계가 작아진다. 이번 실패 원인은 scratch 계측기였으므로 제품의 실패 처리 결함으로 옮기지는 않는다. 보존한 중간 객체는 무과금 gate replay에 재사용했고 그 replay를 새 real-provider 샘플로 집계하지 않았다.

**최신 구현·합의:** #155의 ledger provider `elice`, #156의 dead fine reserve·hardcoded cost 제거는 병합됐고 관련 회귀 PASS다. [#153 Runtime 최신 답변][i153-latest]은 현 Search injected rates 유지, opaque `pricing_id`를 지금 추가, `ELICE_ML_API_KEY` 우선+`GEMINI_API_KEY` fallback을 Search config에서 처리하는 방향에 동의했다. 이 방향을 미결 질문으로 되돌리지 않는다. 현재 [Fine][latest-fine]의 token/cost null과 pricing_id/env 이행 구현·Runtime FinalUsageRecord 보존은 별도 후속이다. 공유 pricing catalog의 영구 소유권이나 USD/KRW 정합은 이 답변으로 확정된 것이 아니다. #157의 google-genai 제거는 pyproject/lock 충돌로 미병합이다.

#### 충돌

**A:** 실제 correction과 자동 workflow 기록, runtime cache와 사용자 history를 구분하면 기존 계약과 정합. **B/C:** 원문 provenance 저장, 최신 #74 Deferred 반영, 보존 결과를 active로 잘못 사용하지 않는 구현. 동의·보관기간을 지금 새로 결정할 이유는 #145에서 발견되지 않았다.

#### 제안안 — 참고

자동 초안 시작은 workflow 이벤트로, 실제 수정은 CorrectionRecord로 기록하는 안을 제안한다. 기존 immutable history는 보존하되 사용자용 결과 재사용 UI는 §27대로 유예한다. #74의 상태만 문서에 동기화하고 승인되지 않은 12개월 보관 숫자를 확정하지 않는다. 근거는 기존 append-only·실제 사용자 provenance·최신 PM 댓글이다. Owner 판단이 우선한다.

#### Owner 질문

**없음.** Q5/Q7의 active basis 규칙을 적용하면 된다. 로그 재사용 정책을 다시 질문하지 않는다.

#### 결정 상태

**A+B/C.** Deferred를 미검토 상태나 새 Flow의 구현 blocker로 되돌리지 않는다.

### D12. Eval / Mock / E2E 회귀 범위

#### #145 변경

F17은 네 사용자 완료 경로를 다시 정의했다. 기존 판독/fixture 단위 PASS만으로 새 Flow 완료라고 선언할 수 없다.

#### 현재 계약/ADR

[Eval 2차 checklist][eval-checklist]의 mock tier는 배관 확인이며 실제 성능 근거가 아니다. candidate rank/Recall@K와 wrong accept/abstention은 별도 지표다. `UNKNOWN` fixture 이름을 실제 어떤 값이 없는지 읽지 않고 새 Product 회귀로 계산하면 안 된다.

#### 현재 구현과 필요한 scenario

| 회귀 경로 | 현재 증거 | 새 Flow에서 필요한 증거 / 담당 |
| --- | --- | --- |
| 정상 자동 초안→handoff | happy fixture와 domain 테스트는 명시 select를 호출. Evidence adapter는 실제 runtime 응답 대신 test-derived CONFIRMED를 공급. #147 real Positive는 Evidence/CaseView까지 가지만 Package blocked, READY 전이는 선행 호출 | raw 입력→실제 scope→rank1 Case 선택→준비→최종 검토 command까지. Case/Web + Eval |
| rank 순서·최신성 | Search rank 계약 검사, relative_rebase stale 표시 있음 | unsorted raw 입력, rank 누락/중복, stale rank1, 여러 run의 rank1, 늦게 완료된 과거 job가 선택을 덮지 않음 |
| rank1 NOT_OBSERVED | Case 두 경로의 synthetic negative tests와 #146 실제 negative 기록. 승인 후 `youtube_clip_01` real-provider 1회도 NOT_OBSERVED→NOT_ASSEMBLED, downstream 미호출. 그러나 CaseView는 READY | 사용자 화면이 오류/영구 진행/완료 Package 오인 대신 선택된 음성 결과와 다음 출구 제공. 자동 순회 채택 시 비용·stop 조건 |
| UNCERTAIN + 무응답 | #147 코드에서 real `EVT_1` + stub Fine 실행: AWAIT 뒤 clip/OCR/time을 모두 실행하고 Evidence assembly 오류. 16.619초 | 정책 결정에 따라 AWAIT 조기 대기 또는 부분 결과를 회귀로 고정, 실제 응답 수집 후 재개, USER_UNSURE 자동 생성 금지 |
| OBSERVED + 무응답 | synthetic은 시각 확보 EVIDENCE PASS. 9/27 real Positive 4건은 시각 미확보로 EVIDENCE/FINAL 모두 UNKNOWN, `PackageNotReady`; 원본 입력 replay도 동일 | D3 결정 뒤 무응답 결과 검토→실제 응답→Package 연결. 시간·자산 facts의 독립 gate도 검증 |
| `unknown_abstain_partial_001` | **plate `88부1234` 존재**, 실제 USER_UNSURE fixture, 시간 값+NEEDS_REVIEW, location null의 WARN Package | 번호판 UNKNOWN Package의 증거로 계산하지 않음. 새 네 plate 상태는 별도 fixture |
| plate UNKNOWN/partial/not-visible/infra | synthetic 실행으로 null/NEEDS_REVIEW 미승격, partial OK 승격, abstain만 reread Need, PlateReadout 없음은 Need 없음, final visibility true/false/미관찰 분리 확인 | D4 outcome와 nullable renderer, 실행 실패 notice, 다른 BLOCK 유지, partial 오수용 방지 |
| 다른 후보 선택 후 handoff | READY 재선택 거부와 후보 삭제를 실행 확인. 실패한 재선택도 CorrectionRecord/case_rev를 남기는 부작용 발견. Prototype은 plate 유지 | READY→새 selection→새 값/근거·옛 값 비승격→새 Package. 동일 차량/다른 차량 각각; 거부 요청 원자성 회귀 |
| 조금 전/후와 값 수정 | R scenario는 **같은 selection의 수동 발생시각 정정**, plate 유지 테스트 | 새 Search hint와 최종 시간 correction 구분, 새 후보면 Q5 정책 적용, full Search 불필요 검증 |
| no result / timeout / cancel / infra | empty, infra, CANCELLED→PARTIAL, runtime budget 단위 테스트 존재 | 이전 후보·draft 보존, 새 intent 재개, budget 소진 후 추가 scope 동의, 독립 실패/정상 빈 결과 구분 |
| 결과 화면 vs Package | Web stage·field state 단위 테스트 존재 | evidence=null 대기, 부분 evidence+package 없음, READY gate, UNKNOWN시각, 실제 action 연결 |
| 최종 영상·plate image | mock DerivedAsset/AssetFacts, local frame capability 테스트 | 실제 export→basis·byte_size·availability→REPORT_VIDEO 관찰→Package→Web 렌더. mock_only fact 제거 여부 표시 |
| 위치 UNKNOWN | no-location policy·CaseView tests, U fixture·#86 완료 | 기존 정합 회귀 유지. 새 plate-null template와 위치-null 조합 추가 |
| 비용·로그 | Usage/Mock 비용 채점, correction export 테스트. 9/27 정상 10요청·15,726 token과 계측 실패 Coarse 5요청·4,984 token 구분. Fine AnalysisRun token/cost null | 자동 후보 선택을 사용자 correction으로 기록하지 않음, 추가 분석 invocation 비용·실패 비용 보존, #153에서 provider 계측→공개 Usage projection 확인 |

#### 충돌

**B:** 제품 완료 경로의 coverage 부족. 기존 fixture가 옛 선택/응답 입력을 전제하는 것은 현재 Accepted 정책 테스트로 유효할 수 있다. 새 정책 결정 전 이를 실패해야 하는 테스트로 바꾸거나 GT를 새 구현 출력에 맞춰 덮으면 안 된다.

#### 제안안 — 참고

기존 계약 회귀를 보존하고 **결정 revision을 붙인 새 Flow scenario**를 별도 추가하는 안을 제안한다. 우선순위는 Q3/Q6 부분 결과·실제 응답, Q4 plate-null, Q5 READY 재선택, Q1 stale rank 순이다. 마지막에 실제 영상의 Positive E2E와 Web action을 연결한다. 각 test에 synthetic/mock_only/real 범위를 표시한다. 해당 Owner의 테스트 설계 판단이 우선한다.

#### Owner 질문

**Q8 — Eval @kim1034, Case @yuusoyeon, Web/Readout @uminshin, Evidence @flosure23:** 결정된 각 경로를 위 표에 매핑해 **제품 journey 회귀와 AI 품질 지표의 실행 담당·fixture 정본**을 나눠 달라. 정책을 Eval이 대신 정하는 질문은 아니다. 이미 있는 fixture 이름만으로 완료 처리하지 않는 것에 대한 검증 계획 확인이다.

#### 결정 상태

**B**, 정책 의존성은 해당 D에서만 결정. develop의 293+39 PASS와 #147의 297+39 PASS는 새 Flow 완료 선언이 아니다. 9/27 실제 Positive 4건은 Evidence/CaseView와 Package 거부 경계까지, negative 1건은 정상 비조립 경계까지다. 계약 validator·보존 입력 replay가 통과해도 Package·handoff 완료와 구분한다. 추가 회귀는 낮은 association 표현, 후보 밖 best frame, 자산 facts 미확보, 같은 입력 영상의 상반된 Fine 반환을 포함한다.

**최신 회귀 보강:** #121의 Exact 기록 요건(정규화·이미지 출처·sample 식별)과 #126의 candidate/classification Wilson 구간은 [현재 Eval 기준][latest-eval-metrics]에 반영됐다. plate 정규화 정책·GT legibility/줄 수 라벨·실제 사용자 journey 부재를 해결한 것은 아니다. 이번 `742ca89` 확대 검사는 Python **723 passed / 1 failed / 3 skipped**, Web **38 passed / 2 failed**다. Readout 실패는 생산 코드 guard 문제, Web 실패는 새 real fixture를 고려하지 않은 개수 assertion으로 나눠 §10에 남긴다. 후자의 실패가 화면 선택 함수 자체의 회귀를 증명하지 않으며, 해당 테스트가 첫 count assertion에서 멈췄으므로 뒤 loop까지 PASS했다고도 주장하지 않는다.

## 6. Owner별 질문 모음

Owner 이름은 [ownership §2][owners], GitHub ID 및 Wireframe 담당은 [#149 본문][i149]과 해당 Owner 댓글을 대조했다. Wireframe은 별도 Architecture module Owner 행이 아니라 Design 산출물 담당이다.

### Search

**서어진 @kong2488-star.** Q1의 현재 run 후보 집합/순위 전달 Consumer 확인, Q7의 scope·budget 경계. rank authoritative 여부는 질문하지 않는다. timeout/factory 제한은 #72/#149/#152, target-localization은 #139, provider/pricing은 #153에서 계속한다.

### Recording

**정철원 @cheol1203.** Q4의 최종 영상 fact 미생산과 실제 false 구분에 필요한 입력 확인. 새 별도 정책 질문은 없다. #47의 export capability와 I4 asset/관찰 접합만 기존 트래커에서 정리한다. canonical frame 원본 좌표계는 재논의하지 않는다.

### Readout

**신유민 @uminshin.** Q4 네 상태의 실제 출력·fact 경계, Q8 partial/abstain/infra 회귀 확인. UNKNOWN/NEEDS_REVIEW enum과 best-frame 계약을 새로 만들지 않는다. #138 런타임 v1.3·frame adapter는 병합됨으로 갱신한다. 2줄 partial 실패와 active mock v1.2 잔존은 정책 질문을 추가하지 않고 §10의 구현·fixture 후속으로 연결한다.

### Evidence

**김준영 @flosure23 — Product/Common 겸임.** Q2 음성 결과 출구, **Q3 실제 상황 응답 gate**, Q4 이미 제시한 UNKNOWN 허용의 미관찰/실패 경계, Q5 correction 적용 context, Q6 결과 최소 보장, Q7 추가 범위 위임. Q3/Q6은 한 답변으로 묶고, Q4는 계약화 범위를 정하면 된다. 위치-null과 기존 USER_UNSURE provenance는 재질문하지 않는다.

### Case

**유소연 @yuusoyeon.** Q1 rank projection/활성 run, Q2 음성 출구, Q3 AWAIT 소비/실제 응답, Q5 selection 무효화, Q6 부분 결과·최종 검토 intent, Q7 새 scope와 보존, Q8 journey regression 담당. 질문 수를 늘리지 않도록 **Q1·Q2, Q3·Q6, Q5·Q7**을 각각 연결해 답할 수 있다. 이미 결정된 resume job identity·부분 재실행 기본표는 유지한다.

### Web

**신유민 @uminshin.** Q1 projection, Q3/Q6 결과·응답·command, Q5 새 selection 표시, Q8 UI 소비 회귀. #106 command 표면을 재사용하며 local 선택 commit이나 UI ranking을 만들지 않는다. #123의 폐기된 StreamScreen 전제는 질문하지 않는다.

### Wireframe

**김대원 @kim1034**, Web 신유민과 결과/후보 UI 경계 협의. Q6 결과 최소 자료가 정해지면 D8 14장 매트릭스로 수정 범위를 정리한다. 개별 문구를 월요일 정책 질문으로 늘리지 않는다. #123 종료에 따라 남은 접합은 #122/#106과 개별 화면 후속으로 추적한다.

### Eval

**김대원 @kim1034.** Q8 결정별 scenario·정본·실행 담당 확인. wrong accept와 abstention, synthetic 통과와 Real E2E를 분리한다. Q1/Q4/Q5의 정책을 Eval 점수로 대신 결정하지 않는다.

## 7. 후속 변경 영향 지도

표의 변경은 **예상 영향이며 승인/구현 명령이 아니다**. `—`는 이 Decision에서 독립 변경 근거를 찾지 못했다는 뜻이다.

| Decision | Search | Recording | Readout | Evidence | Case | Web | Eval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 intake | scope 소비 유지 | 업로드 사실 | presence 사실 유지 | hint를 확정값으로 승격 금지 | 원문/LLM/scope 발주 | 통합 홈·결과 hint 편집 | 오해·low/null 복구 |
| D2 rank | 기존 rank·run 근거 | timeline revision 제공 | — | Fine disposition 유지 | rank/최신성/자동 선택 | rank projection·optional compare | stale/multi-run/negative |
| D3 응답 | Fine 결과 유지 | 선행 clip 허용 범위 | 선행 OCR 허용 범위 | ADR gate·실제 response | AWAIT/응답 재개 | 부분 결과·응답 command | 무응답·실제 응답 |
| D4 plate UNKNOWN | — | final video 사실 | 네 상태·I4 입력 | rule/type/template/builder | field state·Need/경고 | null plate·실패 구분 | 네 상태×fact×template |
| D5 후보 변경 | Coarse 보존 | 새 span/asset | 새 readout | selection basis·correction | READY 전이·rev 격리 | 잠금·새 값/참고 값 | 동일/다른 차량 |
| D6 결과/READY | — | draft asset 의미 검토 | 관찰 projection | ready-only 유지/변경 확인 | 부분 결과·review intent | 결과 composition | gate와 화면 조합 |
| D7 위치 | — | GPS 사실 유지 | — | 현 null/WARN 유지 | 현 projection 유지 | 문구 정렬 | 기존 회귀 유지 |
| D8 화면 | 계약 외 일치 판단 금지 | — | — | 표시용 사실 제공 | command 계약 | 14장/Prototype/Web 정렬 | UI action 회귀 |
| D9 재탐색 | budget/deadline | 원본·완료 자산 보존 | 부분 rerun | 필요한 재계산 | scope/보존/late result | 복구 출구 | cancel/timeout/partial |
| D10 asset/time | Fine span | report/plate export·facts | canonical frame·I4 | timestamp/FINAL rule | 발주·preview projection | report video/원본 구분 | 실제 자산 E2E |
| D11 로그/history | immutable run | asset lifecycle 유지 | immutable run | supersede 보존 | 원문·workflow/correction 구분 | history Deferred | 동의 정책과 평가 분리 |
| D12 검증 | rank/실패 | 실제 자산 | 오수용/abstain | 정책 revision | journey | 실제 action | 정본·실측·coverage |

우선 연결 순서는 **Q3/Q6 결과·응답 → Q4 plate 정책 계약화 / Q5 selection context → #106·#122 projection/command → #47·I4 자산 → D12 네 완료 경로**다. intake·문서 동기화·기존 버그 재현처럼 결정과 독립적인 작업은 병행 가능하다.

## 8. 월요일 회의 안건

**아래는 조건부 목록이다. 별도 일요일 마감은 두지 않으며, 9/28 월요일 회의 전까지 답변으로 닫힌 항목은 회의에서 제거한다.** Owner가 아직 답하지 않은 것을 동의로 간주하지 않는다.

| 우선순위 | 비동기로 닫히지 않았을 때만 논의 | 필요한 결정 산출물 |
| --- | --- | --- |
| 1 | **D3+D6 / Q3+Q6**: 부분 결과·실제 상황 응답·완성 Package의 경계 | 응답 시점, 응답 전 실행 허용표, 결과 최소 자료, Package gate 유지/대체, 실제 최종 검토 intent |
| 2 | **D5 / Q5**: 새 후보와 시간 보정의 correction 적용 범위 | 값별 invalidation 표, 사용자 입력 재적용 여부, READY 재선택/새 review context |
| 3 | **D9 / Q7**: 자동 후속 탐색의 범위 | 기존 scope/budget 내 자동 vs 새 intent 확대 경계. timeout 숫자는 기존 #72/#149 |

Q2 음성 결과 출구는 1번의 결과 종류에 합치고, Q4 미관찰/실패를 WARN으로 허용할지 의견이 갈리는 경우에만 1번 gate 논의에 추가한다. **위치-null, rank 권한, #123의 옛 StreamScreen, 재개 job ID, 로그 retention 숫자, 다중 frame preview를 기본 회의 안건으로 올리지 않는다.**

## 9. 이미 결정되어 재논의하지 않는 항목

| 항목 | 최신 근거와 상태 |
| --- | --- |
| rank authoritative / Web 재계산 금지 | CandidateEvent Final + #145 + #122. 남은 것은 projection/활성 후보 집합 |
| stale 후보 자동 선택 금지 | #145 §4·§8와 #122가 요구. 새로 허락받을 조건 아님 |
| 위치 null WARN Package | ADR-003·#48. #86 fixture/Web 동기화 완료 |
| USER_UNSURE는 실제 사용자 응답 | EvidenceRecord·ADR-005·#146 최신 Owner 답변. 무응답 자동 생성 금지 |
| NOT_OBSERVED 비조립·불필요 downstream 차단 | ADR-007·#137/#142. 자동 다음 후보 순회는 별개 |
| event/pre/post context 세 FINAL rule 제거 | Accepted ADR-005. 자동 선택 UX 변경 때문에 제거한 rule을 이유 없이 복원하지 않음; 사용자 확인 전제만 재검토 |
| 번호판 형식 불일치만으로 hard reject 금지 | Accepted ADR-006, 구현 후속. `바5215` 같은 부분값과 empty/abstain 구분 |
| 번호판 식별 실패 UNKNOWN 경고 허용 방향 | #146 9/25 Product/Evidence Owner 답변. Contract/renderer 미반영과 세부 경계는 D4 |
| 시각 source priority·TIME_HINT_EDIT≠EVENT_TIME_MANUAL | Final TimeResolution. metadata fallback NEEDS_REVIEW, 실제 override provenance |
| 세 readiness gate의 분리 | Final CaseView/Requirement/Package. 화면 통합만으로 합치지 않음 |
| WARN capabilities 유지 | Case decision·#25/#48. WARN 자체를 BLOCK으로 취급하지 않음 |
| 사용자 resume는 새 Job, 자동 retry는 같은 Job의 새 attempt | 9/13 JobExecution 명확화·resume identity decision |
| plate best-frame 입력·canonical 좌표·single preview 기본 | #47 및 PlateReadout best_frame 결정. capability/projection만 후속 |
| overlay 존재 없음 vs 판정 못 함 vs OCR 실패 | Readout failure taxonomy. 새 Flow도 이 사실 구분을 없애지 않음 |
| input model 최신 선택 | #144의 후속 결정. 옛 선택 원문은 이력으로 보존 |
| #123 StreamScreen 초기 제안 철회 | 9/27 closed. 진행/결과 분리·optional compare, 잔여 접합은 #122/#106·Web 후속 |
| #153 단기 pricing/config 방향 | Runtime 후속 댓글에서 injected rates 유지·pricing_id 추가·Elice key+기존 alias 호환 동의. 영구 catalog 소유권·USD/KRW는 별도 |
| #139 hint 없는 Readout 우선 진행 | 9/25 Readout 답변에서 target_hint=None으로 진행 가능, target_hint_used UI는 실제 hint 공급 이후 후속. localization Producer는 여전히 미정 |
| correction 재사용 방향 채택·구현 Deferred | #74 9/20 PM 댓글. 문서의 옛 “미결”로 새 질문 만들지 않음 |
| 결과 cache/history/연속 선택 UI·승인 모드·ETA 유예 | #145 §27. immutable 이력 및 runtime cache는 별개 |

## 10. 기존 Issue/PR 연결

날짜는 GitHub 표시의 UTC를 비교했으며, 필요 일정은 KST로 적었다. issue가 open이라는 사실만으로 모든 하위 결정이 미결이라고 판정하지 않았다.

| Issue/PR | 조사 기준 상태 | 최신 논의로 좁힌 범위 / 이 보고서 연결 |
| --- | --- | --- |
| [#145][pr145] | merged | full diff 기준점. conversation/review/inline 0건. 20 hunk 모두 §2 추적 |
| [#106][i106] | open | 9/23 [최신 댓글][i106-final]: common command surface, 결과 재선택, reject IDs 미채택, TIME 계열 후속. D2/D5/D6/D8 |
| [#122][i122] | open | 9/23 [최신 댓글][i122-latest]: rank1·Case 자동·stale 제외, explicit rank 제안. 9/27 [Case 답변][i122-case]: `candidates[].rank` pass-through·rank 오름차순·최신 Run rank1 자동 선택·`selected` 표현을 **Case 제안**으로 제시, Web 확인 대기. 다중 Run rank 표시는 Search와 미결. 초기 자동 채택 가능 여부 질문 반복 금지 |
| [#123][i123] | closed 9/27 | [종료 댓글][i123-final]: Stream 후보 entry 전제 철회, 남은 접합은 #122/#106·Web 후속. D8 |
| [#146][pr146] | merged 9/27 | develop→main 통합. conversation 1건, inline 17건, review 11건. 9/25 [상황 응답][r146-situation]·[plate UNKNOWN][r146-plate]·[Wireframe][r146-wire]·[frame 경로][r146-frame]·[진행 전달][r146-progress] 답변과 [최종 승인/사용자 E2E 후속][r146-final] 반영 |
| [#147][pr147] | merged 9/27, 측정 head `032efc0` | Positive real Fine/OCR→Evidence 증거와 package progress 수정이 develop에 반영. 당시 Package BLOCKED·READY 의미 문제는 남음. 과거 실측을 최신 코드의 유료 재실행으로 표기하지 않음 |
| [#149][i149] | open | Owner/담당 배분. [Search 답변][i149-latest]은 #152 retry 보강과 별개 factory cap 문제. 9/27 [Case 답변][i149-case]: 요청서 `max_latency_sec` 단일 권위(A안) 동의, timeout 숫자는 여전히 미결. D9 |
| [#25][i25] | closed | 실제 USER_UNSURE generic WARN·field state·capabilities의 기존 근거. D3/D7 |
| [#47][i47] | open | [최신 Recording 답변][i47-final]: canonical best frame+bbox·생성 시점. preview_ref 오해 정정과 새 preview/export 후속. D10 |
| [#48][i48] | open | [Owner 최종 결정][i48-final]: location null/WARN·no-location template, 위치 정책 재질문 금지. D7 |
| [#72][i72] | open | timeout 숫자·fallback/budget. 초기 실측 제안 숫자를 확정값으로 인용하지 않음. D9 |
| [#73][i73] | open | [9/26 Recording 완료 댓글][i73-latest]은 WARN ⑦ 원본 무변형 검증 범위. Case WARN ①·기존 결과 보존까지 종료한 것은 아님. D5/D9 |
| [#74][i74] | closed | [9/20 PM 결정][i74-final]: 정책 방향 채택, 구현 Deferred, retention 숫자 미확정. D11 |
| [#84][i84] | closed | real_e2e location_hint 배선. 새 위치 정책 문제가 아님 |
| [#86][i86] | closed | 최초 정책 양자택일은 철회. [최종 댓글][i86-final]: #97/#118로 P/R·Web·checklist 동기화 완료. D7/D12 |
| [#103][i103] | closed | candidate.at을 Evidence 발생시각으로 덮지 않는 수정. Runtime null과 mock 고정 시각 구분. D2/D10 |
| [#137][i137] / [#142][pr142] | closed / merged | Accepted NOT_OBSERVED 소비 수정. 당시 synthetic 증빙과 #146의 후속 실제 negative 증빙 구분. D2/D3/D12 |
| [#138][pr138] | merged 9/27 | target crop/RecordingFrameSource/v1.3/partial taxonomy 반영. 최신 회귀에서 2줄 guard 실패 확인(D4). preview/export는 여전히 범위 밖(D10) |
| [#139][i139] | open | [Readout 최신 댓글][i139-latest]: hint=None 우선 진행·bbox 최소 형태 방향·hint_used UI 유예. [Case 경계][i139-final]와 함께 해석하며 localization Producer/호출 위치는 미정. D5/D10 |
| [#144][pr144] | merged | LLM 선택 후속 결정·강건성 실험, production intake 배선은 범위 밖. D1 |
| [#152][pr152] | merged 9/27 | retry remaining deadline 전달 및 이번 회귀 PASS. #149 factory cap·Q7 scope 확대 정책은 미해결. D9 |
| [#153][i153] | open | [Runtime 최신 합의][i153-latest]: injected rates 유지·pricing_id 추가·Elice env와 기존 alias 호환. 구현·문서 후속과 영구 SSOT 논의를 분리. D11 |
| [#119][pr119] | merged 9/27 | location search-keyword notice mapping·회귀 PASS. D7/D8 |
| [#120][pr120] / [#121][pr121] / [#126][pr126] | merged 9/27 | Readout 연구 인계·Exact 기록 요건·Wilson 구간. 제품 완료 journey 증거와 구분. D4/D12 |
| [#148][pr148] | merged 9/27 | intake robustness 연구 보강. production 배선 완료 아님. D1 |
| [#155][pr155] / [#156][pr156] | merged 9/27 | provider ledger elice·dead cost/fine reserve 정리. Fine 공개 usage 공백은 남음. D11 |
| [#157][pr157] | open | pyproject/uv.lock 충돌, google-genai 제거 미반영. readout-paddle extra 유지와 함께 이행하는 후속이며 umbrella 정책 안건 아님 |
| [#159][pr159] | merged 9/27 | Recording benchmark·분리 범위 baseline. export/최종 Package 증거 아님. D10/D12 |

### 실행으로 확인된 후속 버그 — Owner별 이슈 초안

아래는 조사 단계에서 작성한 초안이다. 이번 원격 발행 범위는 umbrella와 Case 버그 3개이며, Readout partial guard·Web fixture drift는 이 보고서의 후속으로만 남긴다. 기존 이슈가 소유한 항목에는 연결 메모만 남긴다. `742ca89`의 신규 실행 실패 두 건과 `032efc0`에서 확인한 기존 blocker를 구분하며 정책 질문은 추가하지 않는다.

#### Readout @uminshin — 2줄 번호판 partial guard가 하단 행을 OK로 반환

**제목 초안:** `[Readout] PARTIAL_PLATE_READ 정규식과 best_frame 차단 회귀 복구`

**본문 초안:** develop `742ca89`에서 `.venv/Scripts/python.exe -m pytest tests/readout/test_target_crop.py -q`는 5 PASS / 1 FAIL이다. 기존 테스트 `test_two_line_lower_row_is_partial_not_an_accepted_plate`의 synthetic `바5215` 입력은 기대 NEEDS_REVIEW·abstained=true·PARTIAL_PLATE_READ·best_frame=null과 달리 OK·abstained=false·reason=null·best_frame 있음으로 반환된다. `_abstain_reason()` raw regex의 이중 backslash로 partial guard에 진입하지 못한다. 최신 taxonomy가 이미 해당 보류와 행 bbox 미발행을 명시하므로 정책 재결정 없이 구현 오류로 추적한다. **제안 — 참고:** 해당 regex 의도를 복구하고 공백 변형·정상 전체 plate·숫자-only 보류를 함께 확인한다. Acceptance: 기존 실패 테스트 복구, 부분 행은 값을 보존하되 미확정 및 best_frame 미발행, 정상 전체 plate는 퇴행하지 않음. 실제 2줄 영상 검증은 별도 표본이 필요하며 이 테스트만으로 일반 OCR 품질을 주장하지 않는다.

**같은 Owner의 문서/fixture 후속:** 런타임은 v1.3으로 수정됐지만 active mock `scenario_happy_001`, `scenario_correction_rerun_001`, `scenario_plate_reread_001`(2개), `scenario_unknown_abstain_partial_001`의 5개 PlateReadout은 v1.2다. #146의 기존 version 후속에서 객체 의미·bbox·Consumer 기대값을 확인해 이행한다. 과거 실험 snapshot·정상 Overlay v1.2는 대상이 아니다. 검사 PASS가 이 미동기화를 감지하지 못하므로 버전 헤더/발행값 회귀를 Owner가 검토한다.

#### Web @uminshin / Case @yuusoyeon — real fixture 추가 뒤 고정 개수 회귀 드리프트

**제목 초안:** `[Web] #147 real CaseView 추가에 맞춰 fixture 수와 READY 방어 회귀 갱신`

**본문 초안:** develop `742ca89`에서 `npm --prefix apps/web test -- --reporter=dot`는 38 PASS / 2 FAIL이다. [fixture 로더][latest-web-fixtures]는 커밋된 real JSON 전체를 glob으로 읽지만 [테스트][latest-web-test]는 scenario 8개와 Package 없는 READY 1건을 고정한다. #147의 real JSON 3개가 들어온 현재 관측값은 각각 9개·4건이다(서로 같은 scenario_id를 사용하는 파일이 있어 파일 수와 scenario 수는 다름). `selectScreen`·로더의 구현 diff는 없으며 실패는 두 count assertion에서 난다. **제안 — 참고:** corpus 구성 검사와 각 fixture의 의미 검사를 분리하고, Package 없는 READY에 대한 EVIDENCE 방어를 전체 해당 fixture에서 실행하도록 갱신한다. 개수 검사 자체를 무조건 없애기보다 corpus manifest/의도한 추가를 함께 검증한다. Acceptance: 새 fixture가 등재값 검사를 통과하고 각 화면 선택이 정책대로 검증되며, Package 없는 READY를 HANDOFF로 보내지 않음. Case의 잘못된 READY 발행을 정당화하거나 UI가 임의로 Package를 생성하는 수정은 아니다. 데이터/테스트 후속이므로 월요일 Product 안건에 추가하지 않는다.

정책 Q1~Q8을 이 실행 결과로 닫지 않는다. 아래는 재현 가능한 구현 경계만 이슈 초안으로 분리한 것이다. D2 rank/timeline projection은 기존 #122가 이미 같은 접합부를 다루므로 새 이슈를 중복 생성하지 않고 실행 결과만 그 이슈에 연결한다.

#### Case @yuusoyeon — AWAIT disposition을 Evidence 조립 오류로 소비하지 않기

**제목 초안:** `fix(case): AWAIT_SITUATION_RESPONSE를 real E2E 조립 전에 소비`

**본문 초안:** #147 head에서 Fine을 `UNCERTAIN`, 사용자 응답을 없음으로 둔 real-video stub 실행 시 disposition은 `AWAIT_SITUATION_RESPONSE`였지만 IncidentClip·plate OCR·overlay OCR·TimeResolution을 모두 실행한 뒤 Evidence assembly가 `an uncertain event requires USER_UNSURE context for the v1 fallback`으로 실패했다. NOT_ASSEMBLED와 별도로 AWAIT를 정상 대기/부분 결과로 소비하고, 선택한 Product 정책에 따라 허용된 선행 작업만 실행한다. 무응답을 `USER_UNSURE`로 합성하지 않는다. Acceptance: AWAIT가 일반 오류가 되지 않고, downstream 호출 여부가 Q3 결정과 일치하며, 실제 응답 뒤 같은 selection context로 재개된다.

#### Case @yuusoyeon — 거부된 READY 재선택의 CorrectionRecord 부작용 제거

**제목 초안:** `fix(case): READY 후보 재선택 거부를 원자적으로 처리`

**본문 초안:** READY에서 `correction.reselect_candidate(case, candidate_b)`를 호출하면 domain은 `InvalidTransition`으로 거부하지만 wrapper가 먼저 correction을 적용해 `case_rev`가 3→4로 오르고 `OTHER_CANDIDATE` record가 남는다. 선택과 `selection_rev`는 그대로라 기록과 실제 상태가 불일치한다. stage/candidate 유효성을 mutation 전에 검사하거나 단일 원자적 domain operation으로 묶는다. Acceptance: 거부된 요청은 case_rev·CorrectionRecord·selection에 변화를 남기지 않고, EVIDENCE_REVIEW의 정상 재선택은 기존 provenance를 보존한다. READY 재선택을 새로 허용하는 정책은 Q5/Q6에서 별도 결정한다.

#### Case @yuusoyeon — ReportPackage 없이 READY로 전이하는 real E2E 경로 차단

**제목 초안:** `fix(case): real E2E에서 PACKAGE_READY 전에 mark_ready 호출 금지`

**본문 초안:** #147 Positive 기록은 실제 Fine/OCR/Evidence를 성공했지만 occurred_at·situation_response 부재로 `report_package=null`인데 `CaseView.stage=READY`다. 승인 후 같은 영상의 real-provider 음성 실행도 `NOT_OBSERVED→NOT_ASSEMBLED`, evidence/package null인데 READY를 출력했다. 현재 dump 경로가 disposition/adapter snapshot보다 먼저 `case.mark_ready()`를 호출하는 공통 문제다. Final CaseView 계약에서 READY는 PACKAGE_READY이므로 READY 전이는 Final PASS/WARN + Package 존재 뒤에만 수행한다. 다만 음성 결과와 AWAIT/부분 결과를 어느 stage·화면으로 투영할지는 Q2/Q6 결정에 맡기며 모두 EVIDENCE_REVIEW로 단정하지 않는다. Acceptance: observed/package-blocked와 NOT_OBSERVED fixture 모두 READY를 내지 않고, ready-only happy fixture는 기존 HANDOFF/READY를 유지하며, 각 비완료 disposition은 결정된 화면으로 투영된다.

#### Search @kong2488-star / Eval @kim1034 — 실제 provider usage를 공개 run에 보존

**기존 #153 연결 메모:** 승인 후 실행에서 wrapper는 Coarse 998 token, Fine 3,466 token을 계측했지만 Fine `AnalysisRun.usage_summary.token_usage`와 `total_cost`는 null이었다. 이는 계약 위반이라고 단정할 항목이 아니라 비용·호출량 회귀와 운영 관찰에 필요한 값의 projection 공백이다. #153에서 provider 결과→UsageRecord/AnalysisRun 중 어느 계층이 정본인지 확인하고, 단가가 없는 경우 비용 null과 호출량 보존을 분리한다. Acceptance 초안: 실제 provider token이 있으면 선택된 정본에서 조회 가능하고, 단가 미설정을 0원으로 기록하지 않으며, Consumer/Eval이 중복 집계하지 않는다.

#### Case @yuusoyeon / Readout @uminshin / Recording @cheol1203 — 기존 clip·target 접합 이슈에 실측 연결

**기존 #139/#47 연결 메모:** 9/27 real Positive 4건의 Readout association은 LOW_CONFIDENCE/FALLBACK_ONLY이고 track_ref가 없지만 CaseView plate는 INFO_SOURCE_VERIFIED다. R3은 candidate end 3.800초인데 best frame ref는 원본 3.873초를 가리켰다. 모듈이 이미 기록한 전체 원본 샘플링 단순화의 실제 재현이므로 새 정책 Issue를 중복 발행하지 않는다. Acceptance 참고안: 실제 candidate clip 범위·원본 offset·canonical frame_ref·bbox를 연결하고, 문자 판독과 대상 차량 association의 검토 상태가 Consumer까지 보존되는지 검증한다. 이 표본의 번호판 문자는 직접 프레임과 대조했으므로 다른 차량 오선택이나 오판독이 발생했다고 단정하지 않는다.

**최신 범위 정정:** RecordingFrameSource는 #138에서 병합됐으므로 Case 배선 교체를 기존 접합 후속으로 좁힌다. [#139 최신 댓글][i139-latest]이 정한 hint=None 우선 진행과 target_hint_used UI 유예는 다시 질문하지 않는다. 다만 OCR 값의 확신과 대상 차량 association의 확신을 혼동하지 않는 검수는 별개로 유지한다.

### 근거 탐색의 경계

#47·#139·I4가 이미 소유한 capability 선택은 여기서 새 합의안으로 복제하지 않는다. #86·#74처럼 최신 댓글이 초기 본문과 다를 때는 위 표의 최신 상태를 따른다. 과거 실험 JSON이나 mock PASS가 Final Contract를 자동 대체하지 않는다. 추가 링크 중 #97/#118은 #86 완료 댓글의 병합 근거로만 인용하며 별도 재리뷰 대상으로 확장하지 않았다.

## 11. 완료 조건

### 이 조사 보고서의 자체 검수

- [x] PR #145 before/after blob을 확인하고 20개 hunk의 모든 의미 변경을 F01~F20으로 추적했다.
- [x] Accepted/Final 결정과 후속 Owner 댓글, 미병합 PR 구현을 구분했다.
- [x] 이미 답이 있는 rank·stale·위치·resume·Deferred 정책을 질문에서 제거했다.
- [x] ADR-005 응답 gate, Package ready-only, 옛 후보 값 유지 협의의 재검토 지점을 명시했다.
- [x] AWAIT 소비 누락 등 구현 문제와 Product Decision을 분리했다.
- [x] 14장 이미지·Prototype·Web·stale 문서와 실제 Contract 충돌을 구분했다.
- [x] 질문을 ownership의 실제 Owner/댓글에서 확인한 GitHub ID에 배분했다.
- [x] 각 제안의 근거·영향·한계와 Owner 우선 원칙을 명시했다.
- [x] 필수 6개 Issue/PR을 최종 검수 때 다시 조회했고 conversation·review·inline을 확인했다.
- [x] 월요일 안건은 비동기 미해결 3개 묶음으로 제한했다.
- [x] 상세 보고서와 토론용 Issue Draft를 분리했다.
- [x] develop·#147 테스트/fixture를 분리하고 synthetic, real-video+stub, 선행 Positive, 9/26 1회, 추가 요청에 따른 9/27 5회 실측을 구분했다. 모델 retry는 0회이며, 계측 실패 5회의 이미 소모된 Coarse 호출량도 공개했다.
- [x] OBSERVED 4건의 픽셀 판독·중간 객체·요건 전체·Package 거부·CaseView를 검수했다. contract validator 20건, 원래 입력의 요건 replay 8건, builder 거부 4건의 결과와 한계를 기록하고 정책 미결을 유지했다.
- [x] `742ca89` 최신 diff·병합 상태·후속 댓글을 반영하고 #138/#147/#152의 해결 범위와 잔여 접합을 분리했다. Python/Web 실패도 숨기지 않고 기록했다. 조사·최신화 단계에서는 유료 재호출·코드/계약 수정 없이 문서를 갱신했으며, 이후 별도 요청에 따라 보고서 Draft PR과 umbrella·Case 버그 3개를 발행 대상으로 삼았다.

### Cross-module review의 완료 조건 — 아직 달성한 것으로 표시하지 않음

- [ ] Q1~Q8에 기존 이슈 답변 링크 또는 명시적 결정/Deferred 사유가 연결된다. 무응답을 수락으로 처리하지 않는다.
- [ ] D3/D4/D5/D6/D9의 결정별 Product 문구, Contract/ADR 변경 여부, Producer/Consumer, follow-up 범위가 기록된다.
- [ ] Accepted 결정 변경은 새 결정·supersede/버전 관계로 추적되고 Owner/Consumer가 확인한다.
- [ ] 문서 stale/구현 후속은 기존 #106/#122/#47/#72/#73/#139 등의 트래커와 연결되며 중복 이슈를 최소화한다.
- [ ] D12의 네 완료 경로와 필수 예외가 구현 이슈별 acceptance criteria로 배정된다. Mock 통과·실제 E2E·Owner 수락을 따로 표시한다.
- [ ] 별도 일요일 마감 없이 9월 28일 월요일 회의 전까지 가능한 범위에서 Owner 의견을 받고, 회의에서는 unresolved만 결정한다.

이 보고서 자체의 완료와 새 Product Flow 구현 완료는 별개다. 이 작업에서는 보고서 게시(Draft PR)와 umbrella·Case 버그 Issue 발행까지만 하며, merge·코드·Contract·ADR 변경은 하지 않는다.

<!-- 근거 링크: 모두 조사 기준 commit 또는 실제 discussion/comment를 가리킨다. -->
[flow]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/product/core-user-flow.md
[flow-before]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/e7ed4a4858df4ceff4991090c23d316cfe843ceb/docs/product/core-user-flow.md
[flow-after]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bcab87db7d128696456efd59eaf7183881e20472/docs/product/core-user-flow.md
[product]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/product/product-spec.md
[owners]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/management/ownership.md#L18
[architecture]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/module-architecture.md
[contracts]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/README.md
[scope]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-analysis-scope.md#L1
[candidate-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-analysis-run-candidate-event.md#L218
[visual-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-visual-evidence.md
[caseview]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-job-record-case-view.md#L218
[evidence-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-evidence-record-needs.md
[package-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-requirement-report-package.md#L154
[correction-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-correction-record.md#L23
[time-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-time-resolution.md#L155
[readout-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-plate-overlay-readout.md
[run-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-readout-run.md
[observation]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-observation.md
[source-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-source-asset-media-stream.md
[recording-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-recording-timeline-asset-span.md
[asset-contract]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-analysis-source-derived.md
[jobexec]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-job-execution.md
[usage]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/architecture/contracts/contract-usage-record.md
[case-spec]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/case/tech-spec.md
[case-w7]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/case/design-refinement-w7-baseline.md
[hint-decision]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/case/decisions/intent-hint-robustness-policy.md
[resume]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/case/decisions/job-resume-identity-policy.md
[adr002]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/evidence/adr/adr-first-completion-owner-decisions.md
[adr003]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/evidence/adr/adr-location-absent-package.md
[adr005]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/evidence/adr/adr-event-context-rules-removal.md#L152
[adr006]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/evidence/adr/adr-license-plate-format-review-rules.md#L1
[adr007]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/evidence/adr/adr-not-observed-non-assembly.md
[readout-failure]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/docs/modules/readout/decisions/failure-taxonomy.md#L110
[web-display]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/web/ux/value-state-display.md
[eval-readme]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/eval/README.md
[eval-checklist]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/modules/eval/second-completion-checklist.md
[wire-readme]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/design/wireframe/README.md
[prototype-spec]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/docs/design/PROTOTYPE-SPEC.md
[prototype-machine]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/apps/prototype/src/machine.ts#L176
[case-service]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/case/service.py#L33
[case-domain]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/case/domain.py#L109
[case-view-code]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/src/daesingo/case/view.py#L151
[real-e2e]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/src/daesingo/case/real_e2e.py#L640
[disposition]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/evidence/disposition.py#L48
[assembly]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/evidence/assembly.py#L184
[requirements]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/evidence/requirements.py#L457
[renderer]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/src/daesingo/evidence/policy.py#L44
[readout-code]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/src/daesingo/readout/api.py
[select-screen]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/apps/web/src/state/selectScreen.ts#L41
[evidence-screen]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/apps/web/src/screens/EvidenceScreen.tsx
[handoff-screen]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/bae28184f9940c0da0bce3fe334a1432920bea97/apps/web/src/screens/HandoffScreen.tsx
[pr145]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/145
[diff145]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/145/files
[pr146]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146
[pr147]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/147
[pr147-positive]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/032efc070af2d8252c1180b90075383d7deba511/docs/modules/case/experiments/real-e2e-20260923-youtube-clip-01-observed.md
[pr147-real-e2e]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/032efc070af2d8252c1180b90075383d7deba511/src/daesingo/case/real_e2e.py#L737
[pr147-paddle]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/032efc070af2d8252c1180b90075383d7deba511/src/daesingo/readout/paddle_provider.py#L88
[pr138]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/138
[pr142]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/142
[pr144]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/144
[pr152]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/152
[i25]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/25
[i47]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/47
[i48]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/48
[i72]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/72
[i73]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/73
[i74]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/74
[i84]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/84
[i86]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/86
[i103]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/103
[i106]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/106
[i122]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/122
[i123]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/123
[i137]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/137
[i139]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/139
[i149]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/149
[i153]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153
[i106-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/106#issuecomment-5788064641
[i122-latest]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/122#issuecomment-5787681148
[i123-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/123#issuecomment-5855876531
[i149-latest]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/149#issuecomment-5832506384
[i149-case]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/149#issuecomment-5857086226
[i122-case]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/122#issuecomment-5857157336
[i47-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/47#issuecomment-5666104327
[i48-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/48#issuecomment-5658225684
[i74-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/74#issuecomment-5747808378
[i86-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/86#issuecomment-5750214958
[i138-partial]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/138#issuecomment-5787706487
[i139-recording]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/139#issuecomment-5789741075
[i139-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/139#issuecomment-5798850907
[r146-plate]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105404010
[r146-situation]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105457837
[r146-case-await]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4102164059
[r146-wire]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105665890
[r146-frame]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105617472
[r146-sampling]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4102110772
[r146-progress]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105767047
[r146-version]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#discussion_r4105604756

[latest-target-test]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/tests/readout/test_target_crop.py#L130
[latest-paddle]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/src/daesingo/readout/paddle_provider.py#L216
[latest-deadline-test]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/tests/search/test_provider_bounds.py#L428
[latest-fine]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/src/daesingo/search/fine.py#L190
[latest-dump]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/scripts/dump_real_video_caseview.py#L57
[latest-web-labels]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/apps/web/src/contracts/labels.ts#L109
[latest-web-test]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/apps/web/src/__tests__/caseView.test.ts#L43
[latest-web-fixtures]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/apps/web/src/contracts/fixtures.ts#L31
[latest-eval-metrics]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/docs/modules/eval/metrics/metric-definitions.md
[latest-recording-baseline]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/docs/modules/recording/experiments/w7-baseline-negative-001.md
[latest-intake-research]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/742ca89bd78e5653ca848eaf518c7c9f021a0546/docs/modules/case/research/intent-llm-robustness-test-design.md
[pr119]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/119
[pr120]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/120
[pr121]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/121
[pr126]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/126
[pr148]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/148
[pr155]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/155
[pr156]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/156
[pr157]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/157
[pr159]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/159
[i73-latest]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/73#issuecomment-5844440299
[i139-latest]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/139#issuecomment-5834619257
[i153-latest]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153#issuecomment-5843758581
[r146-final]: https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/146#pullrequestreview-5326518588

# GitHub Issue Draft

> **발행본은 #170을 참고한다.** 아래는 조사 단계의 초안이며, 실제 발행은 결정 카드 목록 #170과 카드 #171·#172·#173으로 재구성됐다(초안 기준 umbrella #164는 대체되어 닫힘).

**제목 제안:** `[Cross-module Review] #145 결과 중심 Core User Flow — 계약·응답 gate·후보 변경 정합성 확인`

## 왜 검토하나요?

#145는 `영상+설명 → AI 후보 탐색·초안 준비 → 결과에서 필요한 수정 → handoff`로 흐름을 바꿨습니다. 사전 AI 범위 승인, 최초 후보 선택, 중간 번호판·상황 승인을 줄이는 방향입니다. 기존 Accepted 계약과 실제 구현·Wireframe을 대조해, 정책 결정과 구현·문서 후속을 분리하려 합니다.

> 제안은 현재 레포 근거를 대조한 **검토용 참고안**입니다. Module Owner의 전문 판단, 기존 명시적 합의, Producer/Consumer 합의가 우선합니다. 제안과 의견이 충돌하면 cross-module/Product Decision으로 논의하며 제안을 정답으로 간주하지 않습니다.

상세 diff·코드·ADR·댓글 근거와 영향 지도는 [상세 검토 보고서](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/blob/codex/core-user-flow-cross-module-review/docs/product/reviews/core-user-flow-cross-module-review-2026-09-25.md)에 있습니다. 아래는 조사 단계의 초안이며, 원격 umbrella 발행본은 Owner 질문 중심으로 축약하고 별도 Readout/Web 버그는 포함하지 않습니다.

## 검토 결과와 남은 결정

**2026-09-27 최신화:** 구현 기준은 develop `742ca89`입니다. #138/#147/#152가 병합돼 Readout v1.3/frame adapter, Positive 실행 증거·package progress, retry deadline을 반영했습니다. #123은 종료됐습니다. 현재 무과금 회귀는 **Python 723 PASS / 1 FAIL / 3 SKIP, Web 38 PASS / 2 FAIL**이며, Readout 2줄 partial guard 실패와 Web fixture 개수 드리프트를 구현 후속으로 남겼습니다. 과거 유료 실측은 #147 `032efc0` 기준으로 구분합니다.

| 항목 | 현재 상태 / 요청 |
| --- | --- |
| D1 분석 전 확인 제거 | Scope 승인 필수 계약 없음. intake LLM·원문 보존·화면 동기화 후속 |
| D2 rank1 자동 선택 | rank 권한·stale 제외는 결정됨. #122에서 rank projection/활성 run 기준 마무리. #147 synthetic 실행으로 Case 변환의 rank·timeline revision 소실 확인. real-provider rank1도 NOT_OBSERVED였으며 자동 다음 후보 정책은 미정 |
| D3 상황 응답 + D6 결과/Package | **기존 Accepted 결정 재검토 필요.** 실제 USER_UNSURE를 만들지 않고 부분 결과에서 응답 후 Package를 완성할지 결정. stub AWAIT 오류 및 real Positive 4건의 무응답·시간·자산 gate 확인. Positive·negative 모두 Package 없이 READY |
| D4 번호판 UNKNOWN | **허용 방향은 #146의 9/25 Owner 답변에 있음.** synthetic 실행으로 catalog·builder·renderer 세 gate와 네 상태의 projection 차이를 확인. 실제 식별 실패와 최종 영상 미관찰/infra 경계만 결정 |
| D5 다른 후보·시간 보정 | 새 후보의 사용자 확정값 승계 범위 확인. READY 재선택 거부가 CorrectionRecord를 남기는 부작용 발견. 기본 참고안은 후보 종속 값 새로 준비, 옛 입력은 참고만 보존 |
| D7 위치 UNKNOWN | **정합·재논의 불필요.** ADR-003 null/WARN 및 #86 동기화, #119 검색어 부재 Web notice 보강 |
| D8 Web/Wireframe | 14장과 Prototype에 옛 확인 동선 잔존. #106/#122 및 위 결정 후 동기화. #123 closed, 재개하지 않음 |
| D9 재탐색·복구 | 기존 scope/budget 안의 자동 탐색과 확대 intent 경계 확인. #152 retry deadline은 해결, factory cap·숫자는 #72/#149 |
| D10 자산·handoff | Positive FINAL의 report-video/첨부 facts·최종 plate 가시성 없음은 유지. #138 clip frame adapter는 구현돼 Case 배선 교체로 범위를 좁힘. #47·I4·#139에서 계속 |
| D11 로그/history | history Deferred 유지. #155/#156 provider/cost 정리 병합. #153 단기 pricing_id·env 호환 방향은 합의됨, Fine 공개 usage·이행 구현은 후속 |
| D12 회귀 | 과거 #147 Positive 4/negative 1 및 중간 객체 검수와 최신 회귀를 구분. #121/#126 지표 보강은 새 journey 완료 증거 아님. 현재 실패 3건은 Readout/Web Owner 구현·테스트 후속 |

## Owner별 확인

- **Case @yuusoyeon / Search @kong2488-star / Web @uminshin:** #122 rank projection과 현재 run 후보 집합, rank1 음성 출구를 확인해 주세요. rank authoritative 여부는 다시 묻지 않습니다.
- **Product/Evidence @flosure23 / Case @yuusoyeon / Web @uminshin:** D3+D6의 실제 응답 시점·선행 작업·부분 결과 최소 자료를 함께 결정해 주세요. ready-only Package를 유지하는 안이 현재 근거와 가까워 보입니다.
- **Evidence @flosure23 / Readout @uminshin / Recording @cheol1203:** D4는 UNKNOWN 허용 여부가 아니라 **식별 실패·미관찰·실행 실패의 처리 경계**와 필요한 Contract 변경 범위를 확인해 주세요.
- **Case @yuusoyeon / Product @flosure23:** D5 옛 직접 입력의 새 selection 적용, D9 scope/budget 확대 경계를 확인해 주세요. 기본안은 자동 승계 금지, 확대 시 새 intent입니다.
- **Web @uminshin / Wireframe @kim1034:** 결정된 경계를 #106 command 및 14장 화면 수정 범위에 매핑해 주세요. 중간 승인 제거를 최종 사용자 확인 자동 생성으로 구현하지 않습니다.
- **Eval @kim1034 및 각 구현 Owner:** 정상 자동 초안·후보 변경·plate UNKNOWN·복구의 네 완료 경로에 실제 회귀 담당과 fixture 기준을 연결해 주세요. 과거 PASS와 최신 부분 실패 결과 모두 새 journey 완료·Owner 수락을 뜻하지 않습니다.

## 실행 근거와 구현 후속

9/26에는 `youtube_clip_01.mp4`를 #147 head에서 1회 실행해 NOT_OBSERVED를 기록했고, **9/27 추가 요청에 따른 5회에서는 OBSERVED 4 / NOT_OBSERVED 1**이었습니다. Positive 4회 모두 실제 OCR `125호1108`→Evidence 이후 FINAL UNKNOWN·Package 거부를 재현했습니다. 시각·사용자 응답 외에도 report video·첨부 facts·최종 plate 관찰이 없어 차단됩니다. Positive 중간 객체 20건 검증 오류 0건, 원래 입력의 요건 replay 8건과 builder 거부 4건도 동일했습니다. 단일 영상 반복을 정확도 수치로 해석하지 않습니다.

정상 추가 5회는 10 calls·15,726 token·112.931초입니다. 먼저 발생한 **scratch 계측 오류 5회의 Coarse 5 calls·4,984 token도 포함하면 이날 실제 15 calls·20,710 token**이며 provider retry는 0회입니다. 그 계측 오류를 제품 실패나 음성 샘플로 집계하지 않았습니다. 단가 미설정으로 비용은 측정 불가입니다.

실행으로 확인한 후속은 ① AWAIT disposition 소비 누락, ② 거부된 READY 재선택의 CorrectionRecord 부작용, ③ Positive·negative 모두 Package 없이 READY가 되는 real E2E 전이, ④ provider token이 Fine AnalysisRun에 투영되지 않는 관측성 공백, ⑤ 후보 밖 OCR frame 및 낮은 association 표현입니다. ①~③은 Case Owner 초안, ④는 기존 #153, ⑤는 #139/#47 연결 메모로 상세 보고서에 적었습니다. 이 결과로 상황 응답 위치·plate 허용 경계·옛 값 승계·자동 탐색 범위를 결정하지 않습니다.

최신 develop에서는 ⑥ Readout의 `바5215` partial guard가 OK·best_frame을 반환하는 오류, ⑦ #147 real fixture 추가에 뒤처진 Web count assertion을 추가 확인했습니다. Readout/Web @uminshin을 중심으로 Case/Eval Consumer와 회귀를 정리하는 후속이며 월요일 정책 질문을 늘리지 않습니다. 이 두 건은 보고서에만 남기고 이번 원격 Issue 4개에는 포함하지 않습니다. 문서 발행 단계에서도 유료 호출·코드/Contract 수정은 하지 않습니다.

## 진행 방식

현재 일요일 늦은 시점이므로 별도 일요일 마감은 두지 않습니다. **9월 28일 월요일 회의 전까지 가능한 범위에서 각 Owner가 의견을 남겨주세요.** 월요일 회의에서는 비동기로 결론이 나지 않은 항목만 다룹니다. 우선 묶음은 ① 상황 응답↔부분 결과↔Package, ② 후보 변경 시 기존 값 적용 범위, ③ 자동 후속 탐색의 scope/budget 경계입니다. 회의 전 닫힌 항목은 제외합니다. #47/#72/#73/#106/#122/#139/#149/#153의 기존 논의를 중복하지 않습니다.

## 완료 조건

- [ ] 질문마다 Owner 답변 또는 기존 결정 링크/Deferred 이유가 남는다.
- [ ] Product·Contract/ADR·구현·문서 후속을 구분하고 변경 담당/범위를 연결한다.
- [ ] Accepted 변경은 명시적인 후속 결정과 Producer/Consumer 확인으로 기록한다.
- [ ] 네 완료 경로와 예외 상태의 회귀 기준을 배정하고, Mock/실제 E2E/Owner 수락을 분리한다.
- [ ] 미해결 항목만 월요일 안건으로 남긴다.

이번 Issue는 토론장입니다. 상세 근거는 연결된 보고서에 유지하며, 이 참고안만으로 코드·Contract 변경이나 Owner 결정을 확정하지 않습니다.
