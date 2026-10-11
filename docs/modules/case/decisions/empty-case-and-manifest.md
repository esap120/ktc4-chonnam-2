# 빈 case 생성과 업로드마다 `manifest_summary` 갱신

> **상태: 결정 · 구현** · 결정일 2026-10-05 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-12 · 8-17(case 쪽)(`design-refinement-w7-baseline.md`), #247 H-2, HTTP API Contract Draft §5.1 · §5.2 · §9(#265)
> case 공개 함수 · aggregate 초기값 · `manifest_summary` 갱신 규칙이라 case 단독 결정 범위다. `failed_file_count`의 의미 · `duration_sec` · `range`는 정하지 않는다(아래 「남은 것」).

## 배경

HTTP API Contract는 case를 **빈 상태로 먼저 만들고**(`POST /cases`, body 없음), 원본 영상을 **파일마다 따로** 등록한 뒤(`POST /cases/{case_id}/sources`), 단서는 분석 시작 command로 받는다(§5.1 · §5.2). 빈 case의 값과 upload가 `manifest_summary`를 어떻게 바꾸는지는 case가 정한다고 남겨 두었다(§9).

지금 case에는 이 흐름이 없다. `CaseAggregate.intake()`는 `hints` · `manifest_summary`를 한 번에 필수로 받고, `CaseStore.register()`는 adapter를 필수로 받는다.

## 결정

1. **`case.create_case(*, store) -> case_id`** — 빈 case를 만들어 등록한다. 초기값은 §5.1 예시와 같다: `case_rev=1` · `stage=INTAKE` · `hints` 네 키 모두 `null` · `manifest_summary={file_count:0, ok_file_count:0, failed_file_count:0, duration_sec:0, range:null}`.
2. **`case_id`는 case가 발급한다** — `case_` + `uuid4().hex`(ASCII 37자).
3. **adapter 없이 등록할 수 있다**(`CaseStore.register(case, adapter=None)`). 선택 전에는 adapter를 조회하지 않으므로(`service._inputs_for()`) `INTAKE` · `SEARCHING` 동안 CaseView가 만들어진다. 선택 뒤에도 adapter가 없으면 `AdapterNotAttached`로 명확히 실패한다.
4. **`case.record_source_registered(case_id, source_asset, *, store)`** — recording이 등록 · 연결한 원본 1개(`SourceAsset` 계약 dict)를 센다. composition root가 recording 등록과 **같은 transaction**에서 부른다.
   - `file_count` +1, `availability=AVAILABLE`이면 `ok_file_count` +1.
   - `failed_file_count` · `duration_sec` · `range`는 바꾸지 않는다.
   - `case_rev`를 올리지 않는다.
   - `INTAKE`에서만 받는다. 아니면 `SourceNotAccepted`(같은 transaction이라 recording 등록도 rollback된다).
5. **빈 case의 `progress`는 8단계 전부 `PENDING`이다.** `file_intake`는 분석 시작으로 `INTAKE`를 벗어날 때 `DONE`이 된다. CaseView 계약 B절 `progress[]` step 집합 규칙 1(「도달 여부와 무관하게 8단계 전부, 도달하지 않은 step은 `PENDING`」) 그대로이고 새 규칙이 아니다. 예전 코드는 `file_intake`를 「INTAKE 완료 즉시 `DONE`」으로 봤는데, 파일을 한 번에 받던 `intake()` 전제였다 — 원본이 파일마다 따로 들어오면 「다 올렸다」는 분석 시작으로만 안다. HTTP API Contract §5.1 예시의 `progress: []`는 「모양만 보이는 예시」라 이 값으로 맞춘다.
6. 기존 `CaseAggregate.intake()`는 남긴다 — fixture · 테스트 경로용이다. aggregate는 밖으로 내보내지 않는다 — composition root는 `case_id`로만 다룬다(`domain.py` `CaseAggregate` docstring, module-architecture §4-모듈5 ⑥).

## 고른 이유 · 고르지 않은 안

**`manifest_summary`를 누가 들고 있나**

| 안 | 판단 |
| --- | --- |
| **case가 업로드마다 갱신해 저장 (채택)** | 집계가 recording의 연결 기록과 같은 transaction에서 바뀌어 어긋나지 않는다. 지금 만들 수 있다. 「어떤 파일이 있나」는 recording, 「몇 개인가」는 case에 있지만 같은 commit이다 |
| CaseView를 만들 때마다 recording의 case–asset 연결에서 계산 | 원본이 한 곳이라 깔끔하지만, recording에 「case의 asset 목록」 공개 함수가 필요하다(8-13과 같은 의존, #246 S-3). recording 작업(#256 · #258) 뒤로 8-12 전체가 밀린다 |

**`case_id`를 누가 만드나**

| 안 | 판단 |
| --- | --- |
| **case (채택)** | aggregate 정체성은 case 소유다. `job_id` · `correction_id`가 `case_id`를 품고, CaseStore MySQL 설계(#267)는 `case_id`를 128자 이하 ASCII로 가정한다 — 형식을 한 곳에서 지킨다 |
| api composition root가 만들어 넘김 | id 규칙이 api에 생기고 case가 그 형식을 다시 검사해야 한다 |

**id 형식** — ULID(#265 예시 `case_01J…` 모양)는 Python 3.12에 표준 구현이 없어 인코더를 직접 둬야 하고(`uuid7`은 3.14부터), 생성 시각이 URL에 드러난다. 정렬 삽입 이점은 이 규모에서 작다. 코드베이스의 다른 id(`job_…_{uuid8}`)와 같은 uuid4로 했다.

**`duration_sec`를 계산하지 않는 이유** — 계약 정의는 「전체 구간 길이」다(CaseView 계약 B절 `manifest_summary` 행). 블랙박스는 전방 · 후방이 **같은 시간대를 동시에** 찍으므로 파일 길이를 더하면 틀린 값(10분 + 10분 = 20분)이 된다. 올바른 값은 recording timeline(배치 · 빈 구간)에서 나오고, 이는 #184에서 recording에 요청한 「timeline 전체 길이」와 같은 정의다. 지금 web은 `duration_sec`를 화면에 쓰지 않는다(`NoResultScreen`은 `ok_file_count / file_count`만).

**`case_rev`를 올리지 않는 이유** — 여러 파일을 동시에 올리면 응답 순서가 뒤섞여, web이 옛 `case_rev`로 분석 시작을 보내 `stale_revision`이 나기 쉽다. `manifest_summary`는 이후 판단의 입력이 아니다(단서 구조화 결과 반영이 `case_rev`를 올리지 않는 것과 같다). 업로드와 분석 시작이 겹치면 그 시점에 commit된 원본까지 들어간다 — 사용자가 올린 파일이라 문제없다.

**`INTAKE`에서만 받는 이유** — product에 분석 시작 뒤 업로드 흐름이 없고, `START_ANALYSIS` 초안도 `INTAKE` 전용이다(8-17, #265 §9 case 결정). 큰 파일을 다 받은 뒤에야 거부되는 것이 아깝다면 composition root가 업로드 전에 `get_view()`의 `stage`로 먼저 걸러도 된다 — case에 따로 함수를 두지 않는다.

## 배선 조건 (recording 리뷰, #270 @cheol1203)

- **입력 형식:** recording 공개 capability는 `SourceAsset` typed model(pydantic)을 돌려준다. `record_source_registered()`는 계약 dict를 받으므로 composition root가 `model_dump(mode="json")`로 바꿔 넘긴다 — 변환은 composition root의 일이고 case는 typed model을 import하지 않는다.
- **같은 transaction의 rollback은 아직 전제다.** 「recording 등록과 case 반영이 한 DB transaction이라 함께 rollback된다」는 recording persistence(RD-17) 구현 뒤에 성립한다. 지금 recording 등록은 process-local이라 case가 `SourceNotAccepted`로 거부해도 recording 쪽 등록은 남는다 — 향후 통합 전제로 구분한다.

## 남은 것

- **`failed_file_count`의 의미** — 계약은 「파일 등록 실패 수」인데 거부된 upload(`422`)는 기록 없이 버려져 셀 수 없다. case 제안은 「손상 파일을 recording이 `UNAVAILABLE`로 등록 · 연결하면 case가 센다」이고 recording · web과 정한다(#265 §9). 그 전까지 0이라 `UNAVAILABLE` · `UNKNOWN` 파일이 오면 `file_count ≠ ok_file_count + failed_file_count`다 — web은 `file_count - ok_file_count`를 「실패」로 계산하지 않는다.
- **`duration_sec` · `range`** — recording timeline 정의가 나오면(#184) 그 값을 옮긴다.
- **분석 시작(8-1)** 때 adapter를 붙이는 지점 · 8-6(CaseStore MySQL, #267)에서 `store`가 `repository, conn`으로 바뀌는 것.
