# Tool Trajectory Review — 경로가 맞았는지 판정하는 절차

> **담당:** 유소연(`case`) · **Consulted:** 김준영(`evidence` — 규정 해석이 필요할 때만)
> **근거 결정:** `cross-cutting-decisions.md` C-3
> **판정자는 규칙을 해석하지 않는다.** `case`는 신고 요건 계산과 시각 출처 우선순위를 만지지 않는다. 판정자는 `evidence`가 내놓은 판정 값을 **확인만** 하고, 해석이 필요하면 `evidence` Owner에게 묻는다. 이 문장이 없으면 이 절차가 `case`의 소유권 규칙을 침범한다.

`pre-deploy-security-review.md`와 형제 문서다. 둘 다 한 모듈 안에서 닫히지 않는 cross-cutting review이고, 배포 전에 표 하나로 닫힌다.

## 1. 왜 결과 지표와 따로 보는가

AI 에이전트 제품 평가에는 서로 다른 두 질문이 있다.

- **결과가 맞았나(outcome)** — Top-3에 정답이 있나, 번호판이 맞나 → `eval`이 채점한다.
- **거쳐온 경로가 맞았나(trajectory)** — 정답을 **맞는 방법으로** 얻었나 → 이 문서.

에이전트는 틀린 경로로 맞는 답을 낼 수 있다.

| 틀린 경로 | 겉으로 보이는 결과 | 실제 상태 |
| --- | --- | --- |
| Fine 검증을 건너뛰고 Coarse만 보고 「신호위반」을 확정했는데 마침 맞았다 | 점수 100점 | 다음 영상에서는 틀린 유형이 나간다 |
| GPS가 없는데 주소를 생성했는데 우연히 맞았다 | 위치 정확 | 다음 사용자에게 틀린 주소가 나간다 |
| 사용자가 「조금 뒤」 하나를 눌렀는데 파이프라인 전체를 재실행했다 | 결과 동일 | 비용·시간이 몇 배 |

이 축이 비어 있으면 **결과 지표만 좋고 경로가 틀린 상태**를 데모 직전까지 아무도 못 잡는다.

`eval`이 이 판정을 맡을 수 없는 이유: `eval`은 `case`·`evidence`를 몰라야 한다(`module-architecture.md` §6-1). 「필요한 단계만 재실행했는가」는 `case`를 알아야 판정할 수 있다.

## 2. 판정 7줄

| # | 판정 항목 | 무엇을 보나 | 근거가 어디 있나 | 실패하면 무슨 뜻인가 |
| --- | --- | --- | --- | --- |
| ① | 필요한 단계만 재실행했는가 | 사용자 수정 1건에 발주된 Job 목록 | `case`의 부분 재실행 정책 표 (`module-architecture.md` §7-4 · `modules/case/decisions/`) ↔ 실제 `JobRecord` | 정책 표와 발주가 어긋남. 비용 누수 또는 stale 결과 |
| ② | Fine을 건너뛰고 법적 유형을 확정하지 않았는가 | 선택된 후보의 `VisualEvidence`가 존재하는가 | `search.verify_visual` 실행 기록(`AnalysisRun`) | Coarse 점수만으로 유형이 나갔다. 「AI가 법적 위반을 최종 확정하지 않는다」 위반 |
| ③ | 번호판에 target · detection · frame 근거가 연결됐고, 불확실하면 포기했는가 | `PlateReadout`의 association·detection·frame_results·abstained | `readout` 출력 | 근거 없는 번호판 문자열. 「값을 만들어내지 않는다」 위반 |
| ④ | GPS 없을 때 주소를 생성하지 않았는가 | GPS `UNKNOWN`인 case의 위치 값 출처 | `recording` GPS 관찰 → `EvidenceRecord.location` | 사용자 단서가 아닌 값이 위치에 들어갔다 |
| ⑤ | 시각의 출처(provenance)가 보존됐고 사후각인 표시가 있었는가 | `TimeResolution.considered[]`·`post_stamp`, Report Video의 provenance | `evidence` 출력 · `recording.export_report_video` | 어디서 온 시각인지 모른다. 사후각인 영상이 원본 화면 시각처럼 보인다 |
| ⑥ | Evidence Rule을 실제 통과했는가 | `RequirementReport`의 PASS/WARN/BLOCK이 Package 생성 전에 계산됐는가 | `evidence.check_requirements` → `PACKAGE_READY` 순서 | 요건 검사 없이 자료가 나갔다 |
| ⑦ | 원본 영상을 덮어쓰지 않았는가 | `ExternalSourceRef`의 체크섬·mtime 전후 비교 | `recording` 원본 무변형 검증 | 제품 불변 경계 「Source video를 덮어쓰지 않는다」 위반 |

②·③·④·⑤·⑥은 `evidence` 규칙과 얽힌다. **판정자는 각 값이 있는지·순서가 맞는지만 본다.** 값이 규칙상 맞는지는 `evidence`의 unit test가 본다.

## 3. 언제 판정하는가

| 회차 | 시점 | 이유 |
| --- | --- | --- |
| 1 | 목데이터 1차 통합 (`ownership.md` §7-④) | 실제 AI 없이 계약이 맞물리는지 보는 시점. 경로는 이때 처음 전체가 돈다 |
| 2 | 데모 직전 | 실제 구현으로 교체된 뒤 경로가 그대로인지 |

주간은 과하다. 위 두 번 외에는 `search`·`readout` 구현이 교체됐을 때 Owner 요청으로 추가한다.

**자동화하지 않는다.** 수동 확인. 나중에 여유가 생기면 ①·②는 자동 판정으로 옮길 수 있다(§5). ①은 2026-09-30부터 orchestration 지표 러너가 자동으로 잰다(§5).

## 4. 판정 기록

| 회차 | 날짜 | ① | ② | ③ | ④ | ⑤ | ⑥ | ⑦ | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-09-15 | WARN | PASS | PASS | PASS | PASS | PASS | WARN | WARN | 1차 Mock Merge(recording→search→readout→evidence→case→web, eval 병행) 직후 판정. 근거는 아래 §4-1. 판정자: 유소연 |
| 2 | | | | | | | | | | |

판정 어휘는 `pre-deploy-security-review.md`와 같다 — **PASS / WARN / BLOCK**. BLOCK은 ②·③·④·⑦(사용자에게 틀린 값이 나가거나 원본이 손상되는 것). ①·⑤·⑥은 WARN으로 기록하고 진행할 수 있다.

### 4-1. 1회차 판정 근거 (2026-09-15, `scenario_happy_001`/`scenario_unknown_abstain_partial_001`/`scenario_plate_reread_001` 기준)

- **① WARN** — `docs/modules/case/doc-research/부분 재실행 정책 표 초안 v1....md` 13행: `EVENT_TIME_MANUAL` → "제자리, 요건 검사만 재발주"가 정책. 그런데 `src/daesingo/case/jobs.py`에 요건 검사 재발주에 대응하는 함수가 없고, `test_scenario_correction_rerun_smoke.py`도 이를 실제로 발주하지 않은 채 완성된 evidence_v2/report_v2 fixture를 직접 대입한다 — 정책 표와 실제 발주 코드 사이의 대응이 코드로 증명되지 않음. Blocking은 아니나(①은 WARN 허용 항목) 실구현 전환 전 확인 필요.
  - **후속(2026-09-19, 이슈 #73):** `real_e2e.py`/`RealAdapter`의 `correction_records` 전달 누락과 `case_rev` 무관 캐시를 수정하고, real E2E 통합 테스트로 증명(PR #94). "요건 검사"는 별도 `JobRecord` 없이 순수 함수 재호출로 처리한다.
- **② PASS** — `data/mock/search/scenario_happy_001.json`의 두 번째 `analysis_run`(`run_id: run_h001_fine`, `operation: VISUAL_VERIFY`, `outcome: SUCCEEDED`)이 선택된 후보(`candidate_h001`)의 Fine 분석 소스(`as_h001_fine`)를 실제로 가리킴 — Coarse만으로 유형을 확정하지 않았다.
- **③ PASS** — `data/mock/readout/scenario_happy_001.json`의 `PlateReadout.target_association`: `status=ASSOCIATED`, `evidence=[{kind: SPATIAL_PROXIMITY, ...}]`로 근거 연결 확인. 불확실 시 포기 쪽은 `scenario_plate_reread_001`의 `EvidenceRecord`(v1)에 `vehicle_number` 키 자체가 없음(abstain)으로 확인.
- **④ PASS** — `data/mock/evidence/scenario_unknown_abstain_partial_001.json`(GPS `UNKNOWN`)의 `EvidenceRecord.location = null` — 값을 만들어내지 않음.
- **⑤ PASS** — 같은 fixture의 `TimeResolution.considered[]`에 후보별 `source.kind`·`value`·`verification`·`used`가 전부 보존됨. `post_stamp: {needed: true, reason_code: "time.no_verified_overlay_present", requires_user_notice: true}`도 존재. 다만 "사용자에게 실제로 보였는가"는 §3 원문대로 사람이 화면으로 직접 봐야 하는 부분이라 이번 판정에는 화면 확인이 빠져 있음.
- **⑥ PASS** — `src/daesingo/evidence/requirements.py::build_report_package()`가 `requirement_report.overall not in {"PASS","WARN"}`이면 `PackageNotReady`를 코드로 강제 — 순서가 구조적으로 보장됨.
- **⑦ WARN** — `ExternalSourceRef`(`src/daesingo/recording/models.py`)가 `{kind, ref}` 포인터뿐이고 체크섬·mtime 필드가 없으며, recording의 `repository.py`/`service.py` 어디에도 파일 I/O 자체가 없음(Mock 단계라 원본을 건드릴 코드 경로가 아직 없음) — 지금 당장 손상 위험은 없지만("건드릴 방법이 아예 없음"), 원본 불변성을 실제로 계측하는 수단 자체가 없어 2차(실구현 교체) 전에 체크섬/mtime 비교 계측을 반드시 추가해야 함.

## 5. 나중에 자동화할 수 있는 것

- **①** — **자동화됨(2026-09-30~10-02):** `scripts/measure_case_orchestration.py`(결과 `docs/modules/case/experiments/orchestration-metrics-2026-09-30.md`). 처음 적은 「`JobRecord`로 대조」는 쓰지 않는다 — 동기 real 경로는 Job 발주 없이 함수 호출로 재실행해 `JobRecord`가 늘지 않아도 Search·Fine·readout이 다시 돌았고(이슈 #73), 요건 검사는 `JobRecord` 없이 순수 함수 재호출이다(§4-1 후속). 그래서 **단계는 함수 호출로** 「더 부르지 않았는가」(지표 ①)와 「덜 부르지 않았는가」(지표 ④)를 정책 표 「다시 도는 것」 칸과 대조하고, **`JobRecord`는 계약이 발주를 정한 곳**(notice 버튼 → CaseView 계약 B절 §7 매핑, 지표 ④-b)에서만 본다.
- **②** — 선택된 후보마다 `VisualEvidence`가 있는지는 `case` 상태 전이 조건으로 강제할 수 있다.
- ③~⑦은 값의 존재 확인이라 unit test로 옮길 수 있으나, 「사후각인 표시가 사용자에게 보였는가」(⑤)는 사람이 봐야 한다.
