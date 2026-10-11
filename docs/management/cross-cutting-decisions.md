# Cross-cutting Decisions — 모듈 경계 밖 운영 책임 11건의 결정 기록

> **상태: 11건 전부 확정.** 회의에서 안건지 추천안대로 확정하고, 회의만으로 닫히지 않던 항목은 2026-09-04 PM 검토로 닫았다. 문서 반영은 2026-09-04에 완료했다.
> **안건지 원본:** `docs/archive/management/cross-cutting-open-items.md` (결정 완료로 닫힘. 왜 이 항목들이 안건이 됐는지는 그쪽을 본다.)
> **이 문서는 결정의 기록이다.** 각 결정이 실제로 사는 곳은 「반영 위치」 열의 문서다. 그 문서가 바뀌면 이 문서를 고치는 것이 아니라 그 문서가 이긴다.

## 이 결정들의 근거

1. **회의 결과** — 회의 노트에 별도로 적힌 몇 줄을 제외하면 11건 모두 안건지의 추천안대로 확정했다.
2. **2026-09-04 PM 검토** — 회의 노트만으로 닫히지 않던 항목(A-2 승인 절차 / A-3 방향 / B-3 근거 / C-1 기록 위치 / C-2 sign-off / C-3 형식·담당 / C-4 정책값·담당)을 확정했다.
3. **`ownership.md` 대조** — C-3 / C-4의 담당은 회의 노트와 달라졌다. 근거는 전부 `ownership.md`의 모듈 소유 항목이다.

---

## 1. 확정 결과 한눈에 보기

| # | 항목 | Primary | Consulted / Support | 확정 요지 |
| --- | --- | --- | --- | --- |
| A-1 | Timeout / Long-running Job Fallback | 유소연 (`case`) | 신유민 (`web`) | 수치는 baseline 실측 후. 표시는 `core-user-flow.md` §7·§22가 이미 정함 |
| A-2 | 챌린저를 "연다"고 선언하는 주체 | 서어진 (`search`) | 김대원 (`eval`) | **PM 승인 필요** (주간 회의 경로) |
| A-3 | `CLAUDE.md` | 김준영 (공통 기반/운영) | 내용 검토 전원 1회 | **규칙 파일 ✗ / 라우터로 만든다** |
| B-1 | Product Spec / Must-Won't 변경 권한 | 김준영 (PM) | — | 최종 승인자 1명 |
| B-2 | 발표·스토리 / 최종 Presentation | 김준영 | 필요 시 각 module Owner | 기존 담당 유지 |
| B-3 | Evidence Rule / 신고요건 변경 서명자 | 김준영 | — | **별도 서명자 없음 + 근거 기록** |
| B-4 | 문서 일관성(docs consistency) | 김준영 | — | 주간 경계 점검에 붙인다 |
| C-1 | Product Validation Owner | 김준영 (PM) | 김대원(측정·분석) · 신유민(UX 관찰) | **결과는 Notion 전용** · 모집은 전원 |
| C-2 | Security / Privacy Review Coordinator | 김준영 (PM/공통 기반) | 각 module Owner self-review | **PASS/WARN/BLOCK 표로 닫는다** |
| C-3 | Tool Trajectory 통과 판정 | **유소연 (`case`)** | 김준영 (`evidence` 규정 해석) | **별도 문서로 분리** · 담당 변경 |
| C-4 | 학습 / 평가 데이터 재사용 정책 | **유소연 (`case`)** | 정철원 (`recording`) · 김준영 (B-1) | **전제 「재사용 한다」** · 담당 변경 |

**회의 노트에서 바뀐 것 2건** — 근거는 `ownership.md`의 소유 항목이다.

| # | 회의 노트 | 확정 | 근거 |
| --- | --- | --- | --- |
| C-3 | 김준영 | **유소연** | `case`가 「모든 작업 발주 · 부분 재실행 정책」을 소유한다. 판정 근거(재실행 정책 표)를 만드는 모듈이 판정한다. 또 `evidence` 규칙을 만든 사람이 통과를 판정하는 이해 상충이 사라진다 |
| C-4 | 정철원 | **유소연** | `case`가 「익명화 학습 로그 내보내기」를 소유한다. 정책이 바뀌면 동작이 바뀌는 코드가 거기 있다. `recording`의 「보관기간과 일괄 삭제」는 원본·사본의 수명이고 correction 로그는 영상이 아니다 |

---

## 2. 항목별 확정 내용

### A-1. Timeout / Long-running Job Fallback

- **Primary:** 유소연 (`case`) / **Consulted:** 신유민 (`web`)
- **원칙:** timeout 수치 자체는 baseline 실측 후에 정한다. 지금 숫자를 박지 않는다.
- **timeout 시 무엇을 보여줄지는 이 안건이 정하지 않았다.** `product/core-user-flow.md` §7(분석 중단 — 부분 결과 + `이어서 찾기` + `조건 수정`)과 §22(결과 없음 — 출구 4개)가 이미 정했고, 안건지가 인용했던 「현재 Candidate + `[직접 타임라인]`」은 1.2 이전 판본의 잔재다. `core-user-flow.md` §22가 「직접 타임라인」 화면을 두지 않는다고 확정했다. 이 안건이 정한 것은 **값의 결정 시점과 담당**뿐이다.
- **반영 위치:** `ownership.md` §3 유소연 ①소유 · `modules/case/decisions/timeout-fallback.md`

### A-2. 챌린저를 "연다"고 선언하는 주체

- **Primary:** 서어진 (`search`) / **Consulted:** 김대원 (`eval`)
- **승인 절차: PM 승인 필요.** 실무적으로는 **주간 회의에 안건으로 올리는 것이 곧 승인 경로**다. `search`가 주간 회의에서 실패 분류 근거와 함께 보고하고 PM이 승인한다. 막기 위한 절차가 아니라 **다른 사람이 모르는 채로 기술 스택이 바뀌지 않게 하는 절차**로 운영한다.
- **판정 근거:** `Failure decides the challenger` 매핑(§3-(1)). v3에 있던 이 표가 v4로 옮겨지지 않았으므로 `modules/search/decisions/challenger-policy.md`로 소유권을 이관했다.
- **반영 위치:** `ownership.md` · `modules/search/decisions/challenger-policy.md` · `project-operating-plan.md` §3·§4

### A-3. `CLAUDE.md` — 규칙 파일이 아니라 라우터로 만든다

회의 결정은 「공용 `CLAUDE.md`를 만들지 않는 방향」이었으나, 두 개의 다른 파일이 한 이름에 묶여 있던 것으로 판명됐다.

| 무엇 | 만드나 | 이유 |
| --- | --- | --- |
| **(a) 제품 불변 규칙 20개 파일** | **✗ 만들지 않는다** | `product-spec.md` §7 + `module-architecture.md` §3의 **복제본**이다. `docs/README.md`의 「다른 모듈의 규칙을 자기 문서에 복제하지 않는다」에 정면으로 걸리고, 복제본은 반드시 원본과 어긋난다. `CLAUDE.md`는 매 턴 컨텍스트에 자동 삽입되므로 모든 대화가 그 비용을 낸다 |
| **(b) 레포 사용 라우터** | **○ 만든다** | 어디에도 복제가 아니고, 없으면 실제로 손해다 — 1,900줄 문서를 통째로 읽거나, `archive/`를 최신 문서로 오독하거나, 미결 칸을 "완성도를 위해" 채운다 |

**만든 파일:** 루트 `CLAUDE.md` 1페이지 — (1) 이 레포가 뭔지 (2) 읽기 라우팅 표 (3) 하지 말 것 (4) 「규칙 원문은 여기 없다」 포인터. **내용 원본은 `docs/README.md`에 두고 `CLAUDE.md`는 얇은 포인터**다 — Cursor·Copilot을 쓰는 팀원은 `CLAUDE.md`를 못 보기 때문이다. 갱신 트리거는 B-4에 흡수한다.

- **Primary:** 김준영 (공통 기반/운영) / **내용 검토:** 전원 1회 (첫 PR에서)
- **반영 위치:** 루트 `CLAUDE.md` · `docs/README.md` 라우팅 표 · `ownership.md` B-4

### B-1. Product Spec / Must-Won't 변경 권한

- **최종 승인자 1명: 김준영(PM).** module Owner가 Product Scope 변경을 제안할 때는 주간 회의에 안건으로 올리고 PM이 승인한다.
- **반영 위치:** `ownership.md` 운영 역할 표 · `product/product-spec.md` 머리말(변경 절차)

### B-2. 발표·스토리 / 최종 Presentation Owner

- **Primary:** 김준영 / **Support:** 필요 시 각 module Owner. 최종 Demo/PPT 숫자의 sign-off도 같은 라인이다.
- **반영 위치:** `ownership.md` 운영 역할 표

### B-3. Evidence Rule / 신고요건 변경의 서명자 — 두지 않는다 + 근거를 남긴다

**배경.** 1.3에는 「서명자 지정」 개념이 있었다. `Evidence Rule / 신고요건 변경 = 평가·QA 담당자`로 **일부러 PM이 아닌 사람**에게 뒀다. 신고요건 규칙은 틀리면 사용자가 실제로 반려당하는 출력이라, 만든 사람이 스스로 승인하면 검토가 형식이 된다는 이유였다.

**현재.** `evidence` Owner가 김준영(PM)이라 구현과 승인이 한 사람에게 겹친다.

**확정: 별도 서명자를 두지 않고 `evidence` Owner가 겸한다.** 6인 팀에서 합리적 선택이다. 다만 겸했다는 사실과 이유를 기록으로 남긴다.

> 1.3의 서명자 분리를 두지 않는다. 이유: `evidence`는 아무도 호출하지 않는 순수 함수 모듈이라 규칙 변경이 테스트로 즉시 검증되고, 6인 팀에 별도 검토자를 뺄 여유가 없다. 대신 신고요건 규칙이 바뀌면 주간 회의에 보고한다.

마지막 문장이 이해 상충을 실질적으로 완화하고, A-2의 승인 경로와 같은 리듬이라 추가 부담이 없다. 또 C-3 담당을 `case`로 두면서 **규칙을 만든 사람이 아닌 사람이 규칙 통과를 판정하는 구조**가 회복된다.

- **반영 위치:** `modules/evidence/decisions/no-separate-signoff.md` · `ownership.md` §6 · `project-operating-plan.md` §4

### B-4. 문서 일관성(docs consistency) 소유자

- **Primary:** 김준영 — `ownership.md` §6의 주간 경계 점검과 같은 리듬에 붙인다.
- **점검 범위:** 문서 간 포인터가 실제로 존재하는가 / 같은 결정이 두 곳에서 다르게 말하는가 / `CLAUDE.md`·`docs/README.md` 라우팅 표가 현재 폴더 구조와 맞는가(A-3 흡수).
- **반영 위치:** `ownership.md` §6
- **루트 README 사실 절 갱신(2026-10-06, 멘토 리뷰 PR #66):** `.claude/skills/update-readme/` skill과 PR 템플릿 체크 한 줄로 운영한다. 대조 범위 · 원천은 skill 파일이 소유한다.

### C-1. Product Validation Owner — 결과는 Notion 전용

- **Primary:** 김준영(PM) / **측정·분석:** 김대원(`eval`) / **UX 관찰:** 신유민(`web`)
- **모집 방식(회의 추가):** 전원이 각자 지인에게 추천한다. 모집은 전원 분담, 진행·분석 책임은 Primary.
- **기록 위치: 검증 결과·제품 지표는 팀 Notion에만 둔다.** git에는 **계획만** 남긴다. 퍼블릭 레포에 인터뷰 응답이 노출되는 경로를 원천 차단한다.
- `product/user-validation-plan.md`는 git에 유지한다 — 본문은 모집 채널·질문지·관찰 항목뿐이고 개인정보가 없으며, `product-spec.md` §1이 이 문서를 가리킨다. **§6의 결과 입력 칸만 Notion 포인터로 바꿨다.**
- 집계 지표(작업시간 · 후보 수 · 수정 횟수 · handoff율)는 개인 식별이 안 되므로 **결과가 나온 뒤 공개 여부를 따로 판단**한다. 지금 정하지 않는다.
- **반영 위치:** `ownership.md` 운영 역할 표 · `product/user-validation-plan.md` §6

### C-2. Security / Privacy 최종 Review Coordinator — PASS/WARN/BLOCK 표로 닫는다

- **Review Coordinator:** 김준영(PM/공통 기반) / **각 module Owner:** 자기 영역 self-review 및 수정 책임

배포 전 보안 점검은 여러 사람에게 흩어져 있다(파일 삭제 = recording / 외부 AI 전송 = search / 인증 = case·공통 / 신고정보 = evidence / 프론트 키 = web). 체크박스만으로는 「아직 안 봤나 / 봤는데 체크를 안 했나」를 구분하지 못하고, 「아직 위험한데요」라는 말에 배포를 멈추는 힘이 있는지도 정해져 있지 않았다.

**확정: 새 문서를 만들지 않고 `pre-deploy-security-review.md`의 체크리스트를 `항목 / 담당 Owner / 확인일 / 판정` 표로 바꿨다.**

- **판정 어휘는 PASS / WARN / BLOCK** — 제품이 신고요건 점검에 이미 쓰는 어휘다(`module-architecture.md` §4-모듈4 ⑤). 같은 말을 두 곳에 쓰면 팀이 새로 외울 게 없다.
- **BLOCK 대상은 좁게:** 키 노출 · 인증 우회 · 원본 영상 유출 · 삭제 미동작. 나머지는 WARN(기록하고 진행).
- Coordinator가 할 일은 **"BLOCK이 0인가" 확인 하나**로 끝난다.
- **반영 위치:** `management/pre-deploy-security-review.md` · `ownership.md` 운영 역할 표

### C-3. Tool Trajectory 통과 판정 — 별도 문서 + 담당 유소연

**목데이터 통합 통과 기준에 흡수하는 안은 폐기.** 통합 체크와 경로 판정이 뒤엉킨다. **별도 문서로 뺐다.**

AI 에이전트 제품 평가에는 서로 다른 두 질문이 있다. **결과가 맞았나(outcome)** — Top-3에 정답이 있나, 번호판이 맞나 — 는 `eval`이 채점한다. **거쳐온 경로가 맞았나(trajectory)** — 정답을 맞는 방법으로 얻었나 — 는 소유자가 없었다. 에이전트는 틀린 경로로 맞는 답을 낼 수 있다(Fine을 건너뛰고 확정했는데 마침 맞음 / GPS 없이 주소를 생성했는데 우연히 맞음 / 「조금 뒤」 하나에 파이프라인 전체 재실행). 이 축이 비어 있으면 결과 지표만 좋고 경로가 틀린 상태를 데모 직전까지 아무도 못 잡는다.

**Primary: 유소연 (`case`)** — 판정 근거인 「부분 재실행 정책 표」를 만드는 모듈이고, 경로 전체를 아는 유일한 지휘자이며, 목데이터 1차 통합 담당이라 판정 시점이 겹친다. `eval`은 `case`·`evidence`를 몰라야 하므로 구조적으로 맡을 수 없고, `evidence` Owner가 맡으면 자기가 만든 규칙을 자기가 통과 판정하게 된다.

**Consulted: 김준영 (`evidence`)** — 규정 해석이 필요할 때만.

> ⚠ **판정자의 경계.** `case`는 「신고 요건 계산 / 시각 출처 우선순위」를 만지지 않는다. 따라서 판정자는 **규칙을 해석·계산하지 않고 `evidence`가 내놓은 판정 값을 확인만 한다.** 해석이 필요하면 `evidence` Owner에게 묻는다.

- **판정 7줄 · 시점(목데이터 1차 통합 1회 + 데모 직전 1회) · 기록 표**는 `management/tool-trajectory-review.md`에 있다.
- **반영 위치:** 신규 `management/tool-trajectory-review.md` · `ownership.md` 운영 역할 표

### C-4. 학습 / 평가 데이터 재사용 — 전제 「재사용 한다」 + 담당 유소연

| 무엇 | 소유 | 근거 |
| --- | --- | --- |
| **correction 로그의 내용·익명화·export 동작** | **유소연 (`case`)** | `case` 소유 「익명화 학습 로그 내보내기」 |
| 원본·사본이 얼마나 남는가 | 정철원 (`recording`) | `recording` 소유 「보관기간과 일괄 삭제」 |
| 익명화 도구(마스킹 로거) | 김준영 (공통 기반) | 공통 기반 소유 「마스킹 로거」 |
| 사용자에게 뭐라고 약속하는가 | 김준영 (B-1) | Product Spec 승인 |

**정책 전제: 「재사용 한다」.** 실제 서비스 운영 시나리오를 산정해보는 것이 이 프로젝트의 목적 중 하나이므로, 재사용을 전제로 놓고 동의 · 익명화 · 철회 · 보관을 전부 설계한다. 「재사용 안 함」으로 두면 그 설계를 통째로 건너뛰게 되어 운영 시나리오를 배울 수 없다.

**단 재사용을 두 단계로 나눠 전제한다 — 동의 수준이 다르다.**

| 단계 | 무엇에 쓰나 | 상태 | 10주 내 |
| --- | --- | --- | --- |
| **1단계 — 평가 재사용** | 우리 팀이 채점 · hard-negative 후보 · 실패 통계에 쓴다 | `module-architecture.md` §9-5가 경로 설계 완료 (`case` → 익명화 파일 → `eval`) | **구현** |
| **2단계 — 학습 재사용** | 모델 fine-tuning의 학습 데이터로 쓴다 | §10-3 `[미결 유지]`의 fine-tuning과 연결. 경로 없음 | 전제만 |

**고지 문구는 처음부터 두 단계를 구분해서 쓴다.** "AI 개선에 활용됩니다" 한 줄로 뭉뚱그리면 2단계를 열 때 동의를 다시 받아야 한다.

**`case` Owner가 설계할 5개 (초안 → PM B-1 승인):** ① 동의 문구 + 동의 상태 저장 위치 ② 익명화 수준(§3-(2)의 3줄 복원) ③ correction 로그 보관기간(원본 영상과 수명이 다르다) ④ 철회 시 이미 내보낸 로그 처리 ⑤ 1단계/2단계를 구분한 고지 문구.

- **반영 위치:** `product/product-spec.md` §7(사용자 약속 1줄) · `management/pre-deploy-security-review.md`(담당 case) · `modules/case/decisions/correction-log-reuse.md`

---

## 3. v3 → v4 교체로 생긴 공백 — A-2 / C-4의 선행 조건

`module-architecture.md`를 v3 → v4로 교체하면서 **두 절이 v4에 옮겨지지 않았다.** v4가 「세부는 Owner의 Data Contract로 내린다」는 기조이므로 **모듈 Owner의 `decisions/`로 소유권을 옮겼다.**

### (1) `Failure decides the challenger` 매핑 — A-2의 판정 근거

v3 §11-1-1이 소유하던 6행 표와 원칙 2개(「베이스라인이 충분하면 model hunting보다 E2E 완성」 / 「failure category가 지목하는 챌린저만 연다」)는 **`modules/search/decisions/challenger-policy.md`**로 옮겼다. 이 절을 가리키던 `product-spec.md`·`project-operating-plan.md`·안건지의 포인터 3곳을 그쪽으로 고쳤다.

### (2) `export_learning_log()` 익명화 구체 규칙 — C-4의 판단 근거

v3 §9-4의 3줄(번호판 문자열 제거 / 정확한 좌표 제거 / 원본 참조는 로컬 케이스 ID로만)은 v4 §9-5가 한 문장으로 압축하고 구체 필드를 Data Contract로 미뤘다. C-4가 「재사용 한다」로 정해졌으므로 이 3줄은 유예할 수 없다. **`modules/case/decisions/correction-log-reuse.md`**에 복원했다.

---

## 4. 반영 위치 총정리

| 파일 | 반영한 항목 |
| --- | --- |
| 루트 `CLAUDE.md` (신규) | A-3 |
| `docs/README.md` | A-3 라우팅 표 |
| `management/tool-trajectory-review.md` (신규) | C-3 |
| `management/ownership.md` | A-1 · A-2 · A-3 · B-1 · B-2 · B-3 · B-4 · C-1 · C-2 · C-3 · C-4 (운영 역할 표 + §6) |
| `management/pre-deploy-security-review.md` | C-2(표 전환) · C-4(담당) |
| `management/project-operating-plan.md` | A-2 · B-3 · B-4 (주간 리듬) · §3-(1) 포인터 |
| `product/product-spec.md` | B-1(변경 절차) · C-4(사용자 약속) · §3-(1) 포인터 |
| `product/user-validation-plan.md` | C-1 (§6) |
| `product/core-user-flow.md` | §24·§26 포인터 |
| `modules/case/decisions/timeout-fallback.md` (신규) | A-1 |
| `modules/case/decisions/correction-log-reuse.md` (신규) | C-4 · §3-(2) |
| `modules/search/decisions/challenger-policy.md` (신규) | A-2 · §3-(1) |
| `modules/evidence/decisions/no-separate-signoff.md` (신규) | B-3 |
| `archive/management/cross-cutting-open-items.md` | 안건지 이동 · 결정 완료 표기 |
