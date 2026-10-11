# evidence 1차 Mock 통합 수행 결과

> 상태: **PARTIAL_READY**
>
> 최신 실행 기준: branch `codex/evidence-integrated-pr`, 구현 기준 커밋 `78904bd46dd3582cbd0701c31b98d633b4644eb1`, 실행일 `2026-09-15`
>
> 기준 계약/정책: `time-resolution/v1`, `evidence-record/v1.3`, `evidence-needs/v1`, `requirement-report/v1`, `report-package/v1.1`, `correction-record/v1.1`, `policy/requirement-rules-v4`, `safety-report-policy/v1.1`

원본 [`first-completion-checklist.md`](first-completion-checklist.md)의 완료 정의와 작성 시점은 수정하지 않았다. 이 문서는 수행 결과만 별도로 연결한다. production/runtime 완성, 실제 AI·OCR·영상 생성, 외부 제출, 실제 `case`/web projection은 이 결과가 증명하지 않는다.

> **ADR-EVIDENCE-005 반영 완료 (2026-09-14).** `FINAL_PACKAGE`의 사건 장면·전 상황·후 상황 세 rule을 제거한 `policy/requirement-rules-v4`를 활성화했다. H는 `PASS`, U는 `WARN`으로 각각 Package가 발행된다. 경찰민원24 요건 자체가 사라진 것은 아니며 사건 선택·상황 확인은 사용자, 신고영상 전후 포함 보장은 `recording`이 맡는다. 녹화 경계 처리(D2-e)는 `recording` 미결이다.

## 실행 결과 요약

| Scenario | baseline 결과 | Consumer Mock 판독 | 판정 |
| --- | --- | --- | --- |
| H `scenario_happy_001` | Time `OK`; Evidence `ev_h001`; Requirement `PASS/PASS`; `pkg_h001` 1건 발행 | `EVIDENCE_SUFFICIENT=true`, `PACKAGE_READY=true`; `USER_REVIEWED=CASE_OWNED_NOT_DERIVED` | v4에서 세 check가 사라져 FINAL_PACKAGE가 `UNKNOWN → PASS`. 공용 CaseView의 `NOT_ASKED` 경로는 계속 fail-closed이며 test-derived `CONFIRMED` 경로만 Package를 발행 |
| U `scenario_unknown_abstain_partial_001` | Time `NEEDS_REVIEW`; visual type `null`; `USER_UNSURE`; Requirement `WARN/WARN`; `pkg_u001` 1건 발행 | `EVIDENCE_SUFFICIENT=true`, `PACKAGE_READY=true` | v4에서 세 check가 사라져 FINAL_PACKAGE가 `UNKNOWN → WARN`. 위치 부재와 사용자 불확실성 WARN은 유지 |
| P `scenario_plate_reread_001` | `ev_p001` 번호판 부재 + `PLATE_REREAD` + UNKNOWN → `ev_p001_v2` 번호판 `17나2867` + 빈 Needs + Requirement `WARN` | 현재 Evidence는 v2, Package 없음 | v4 EVIDENCE catalog 연결 검증 완료. FINAL_PACKAGE는 Scenario 범위 밖이므로 변화 없음 |
| R `scenario_correction_rerun_001` | Time `NEEDS_REVIEW` → `OK/AGREED/USER_OVERRIDE`; Evidence/Requirement supersede; Requirement `WARN/WARN`; 번호판 `34나7890`·basis·`selection_rev=1` 보존 | 현재 Evidence/Requirement는 v2, Package 없음 | v4 EVIDENCE catalog 연결 검증 완료. FINAL_PACKAGE는 Scenario 범위 밖이므로 변화 없음 |

고정 출력은 [`artifacts/first-completion/run-summary.json`](artifacts/first-completion/run-summary.json)과 같은 폴더의 네 `*.baseline.json`이다. 각 파일은 원본 recording/search/readout/case JSON 경로, candidate Fine run, timeline revision/range, correction refs, 실제 출력 다섯 배열, 공용 evidence Fixture와의 비교, Consumer Mock 판독을 함께 기록한다.

## 처리 경계

- **실제 baseline 처리:** 시간 source 우선순위/offset/충돌, Evidence 조립, CorrectionRecord head와 타입 검증 및 반영, declarative Needs, 활성 catalog 기반 두 scope rule 선택, K1 첨부·K2 기한 평가, deterministic report rendering, ready-only Package 조립.
- **공용 Mock 입력:** recording/search/readout/case의 계약 JSON과 AssetFacts. 원본 46 JSON/7 Scenario는 수정하지 않았다. H의 공용 `NOT_ASKED` 경로는 specific renderer에서 차단한다.
- **evidence 전용 case context:** H의 specific Package 성공 경로에는 `CONFIRMED`, U의 snapshot에는 `USER_UNSURE`의 전체 필드를 test-derived 입력으로 명시한다. 공용 case 원본과 동일하다고 주장하지 않는다.
- **관찰 fact 경계:** 사건 장면·전 상황·후 상황 세 rule과 입력 key는 v4에서, 최종 신고용 영상의 번호판·시각 표시 가시성 두 rule은 v6에서 제거됐다(ADR-EVIDENCE-010, #280). 남은 사후 각인 fact는 boolean·`subject_refs` 구조를 계속 검증하며 문자열 값으로 PASS를 만들지 않는다. 제거된 legacy key가 들어와도 선택 rule이 없어 판정에 영향을 주지 않는다.
- **Runtime 한계:** v6부터 무조건 관찰 rule이 없어 H는 관찰 입력 없이 Package가 나온다. U의 사후 각인 fact(`post_stamp_applied`)는 여전히 adapter가 `mock_only: true`로 주입한다 — 실제 Runtime에서는 recording(C-07)이 그 사실을 전달하기 전까지 사후 각인 갈래가 `UNKNOWN`이다. 이번 Package 발행은 Runtime 준비 완료 증거가 아니다.
- **Consumer Mock:** 공개 Contract JSON만 읽어 current head와 두 gate를 계산한다. CaseView를 만들거나 case 정책을 재구현하지 않으며 `USER_REVIEWED`는 산출하지 않는다.
- **Fixture 비교:** 실제 baseline 처리 후 상태/overall을 공용 evidence JSON과 비교한다. `scenario_id`별 canned output 재생을 처리 구현의 증거로 사용하지 않는다.
- **후속 방어 경계:** Package 조립 전에 RequirementReport 구조와 평가 자산 ref 포함 관계를 검증한다. 평가하지 않은 자산으로 바꿔 끼운 Package는 `package.requirement_asset_basis_mismatch`로 차단하며, null·빈 차량번호는 EVIDENCE `PASS`가 아니라 `UNKNOWN`이다.

공개 사용자는 `daesingo.evidence`에서 순수 함수를 import하고 Final Contract payload를 직접 넘긴다. 자세한 함수 목록과 명령은 [`src/daesingo/evidence/README.md`](../../../src/daesingo/evidence/README.md)에 있다. Mock adapter의 `scenario_id`, 출력 ID, 평가 시각, rule 목록은 [`tests/evidence/fixtures/adapter_inputs.json`](../../../tests/evidence/fixtures/adapter_inputs.json)에만 있으며 Runtime 필드가 아니다.

## 체크리스트 추적표

| 체크리스트 위치/항목 | 구현·검증 위치 | 증빙 | 상태 | 남은 일/담당 |
| --- | --- | --- | --- | --- |
| 회의 핵심·Input·Core Flow: H/U/P/R 계약 입력과 차이 보존 | `mock_integration.py`, `assembly.py`, `time_resolution.py` / `test_mock_integration.py` | 네 Scenario baseline JSON의 `input_trace`, `outputs`, `comparison` | Mock 연결 검증 완료 | 실제 case 호출은 유소연 통합 대기 |
| Output Contract: 다섯 Contract와 ref/provenance/timeline | `validation.py`, `assembly.py` / `test_contract_validation.py` | 모든 생성 Contract validator 통과; artifact의 timeline revision/range | 검증 완료 | validator는 전체 JSON Schema·Owner 수락을 뜻하지 않음 |
| Failure/Partial: UNKNOWN/BLOCK/실패/ready-only | `requirements.py`, `errors.py` / `test_contract_units.py` | UNKNOWN/BLOCK 구분, 누락·불가 자산, 조립 실패, policy data 부재 시 미발행 검사 | 검증 완료 | 실행 lifecycle은 case/runtime 범위 |
| State/Lifecycle: immutable snapshot·supersede·selection_rev | `time_resolution.py`, `assembly.py`, `corrections.py` / 두 test 파일 | P/R 전후 JSON 및 literal 비교 | 검증 완료 | 실제 저장소 durability는 범위 밖 |
| TimeResolution 상세 | `time_resolution.py` / Scenario·UNKNOWN 단위 검사 | H/P OK, U/R-v1 NEEDS_REVIEW, R-v2 USER_OVERRIDE; no-source UNKNOWN | 검증 완료 | Q3은 기존 provenance ref로 추적 |
| EvidenceRecord 상세·초기 4종 매핑 | `assembly.py`, `policy_data.json` / renderer·correction 단위 검사 | U null+USER_UNSURE, R correction ref, 4종 mapping/길이 | 검증 완료 | 실영상 AI 정확도는 미검증 |
| EvidenceNeeds 상세 | `calculate_evidence_needs` / P Scenario 검사 | 첫 basis `ev_p001`, PLATE_REREAD; v2 basis와 빈 items | 검증 완료 | 재발주 변환은 case 담당 |
| RequirementReport 두 scope·우선순위 | `requirements.py`, `policy_catalog.py`, `deadline.py` / Scenario·정책 단위 검사 | EVIDENCE 4개, FINAL 12+조건부 1개; K1 경계·K2 날짜·precedence | 검증 완료 | I4는 번호판·시각 관찰 전달 범위로 유지 |
| ReportPackage ready-only·template·optional plate image·lineage | `requirements.py`, `policy.py`, `validation.py` / D1·계약 단위 검사 | `location:null`, no-location template, v1.1 validator, optional plate image, supersede ref | 검증 완료 | 공용 fixture 재렌더와 case 고지/field state는 I2·case 담당 |
| Integration: Consumer가 공개 출력 읽기 | `consume_contracts` / Scenario 검사 | 각 baseline JSON의 `consumer_mock` | Mock 연결 검증 완료 | 실제 CaseView projection은 유소연 통합 대기 |
| Operational: revision·정책·Mock 범위·재현 | CLI, artifact, 이 문서 | `base_revision`, `execution_mode`, source paths, 아래 명령 | 검증 완료 | Artifact는 후속 방어 경계와 정적 검사 정리를 포함한 `78904bd` 기준으로 재생성 |
| K1 첨부 용량·개수 | `attachment_policy_v1.json`, `requirements.py` | exact limit·1 byte 초과·null·부분합·dedup·개수·구성 오류 | 정책 엔진 반영 및 단위 검증 완료 | 실제 외부 제한 변경은 새 policy version 필요 |
| K2 신고기한 | `deadline_policy_v1.json`, `deadline.py` | 평일·금요일·연속 공휴일·연말·exclusive 경계·coverage 오류 | 정책 엔진 반영 및 단위 검증 완료 | 2028 이후 calendar revision 필요 |
| K3·D2 rule catalog | `requirement_rules_v4.json`, `policy_catalog.py`, `requirements.py` | scope 수·조건부 selector 네 갈래·세 rule 부재·legacy 입력 무영향·출력 policy_ref | 활성 v4 연결 및 검증 완료 | v2는 첫 실행 전 대체, v3는 실행 후 D2로 대체된 revision으로 보존 |
| K4 correction provenance | `source-kind-registry.md` v2, `assembly.py` / correction 단위 검사 | 비시각 9개 path의 kind/ref/OBSERVED/null label/user flags, 파생값 INFERRED, occurred_at 무변경 | registry 추인 및 단위 검증 완료 | 실제 Consumer 검증은 I7·I8 대기 |
| D1 위치 없는 Package | 계약 v1.1, 신고문 정책 v1.1, catalog v4, package/validator 구현 | 공용 U의 `location:null`, no-location template, `WARN`, `pkg_u001` | 네 층 반영 및 Mock 연결 검증 완료 | 공용 fixture의 v1/no-location 미반영은 I2 대기 |

체크리스트 원문의 체크박스는 일괄 변경하지 않았다. 위 표의 “검증 완료”는 해당 코드/Contract 단위에 한정하며 공용 E2E, production, Consumer Owner 수락으로 확대하지 않는다.

## Q1·Q2·Q3 및 후속 작업

| 항목 | 최신 확인 | 영향 | 필요한 조치 / 담당 |
| --- | --- | --- | --- |
| Q1 U의 `report_inputs.location=null` | **종결.** ADR-EVIDENCE-003에 따라 `report-package/v1.1`에서 키 필수·값 nullable이며 위치 부재는 WARN이다 | D1 단위 경로에서 정상 Package가 발행된다 | evidence 네 층 반영 완료. `CaseView.report_field_states.location`, 고지 code, 공용 fixture 재렌더는 case/I2 담당 |
| Q2 H/U 문구·Template·policy provenance | `safety-report-policy/v1.1`과 장소 없는 template을 발행했다 | 새 Package는 선택 template과 v1.1 policy ref를 보존한다 | evidence 구현 완료, 공용 Fixture 동기화는 I2 담당 |
| Q3 timeline revision 직접 필드 | TimeResolution에 새 직접 필드는 확정되지 않았다 | CandidateEvent span과 IncidentClip provenance의 timeline ref/revision/range로 사용 입력 추적 가능 | 비차단 후속. 새 필드 없이 현 경로 유지; Contract 변경 시 반영 |
| 공용 H/U Package baseline | **반영 완료.** 판정 주체가 없던 세 rule을 v4에서 제거했다 | H `PASS`·`pkg_h001`, U `WARN`·`pkg_u001`; 두 Consumer Mock 모두 `PACKAGE_READY=true` | evidence 범위 완료. 공용 Package는 아직 v1이고 U는 위치 있는 template이므로 I2 fixture 재렌더 대기 |
| D2-e 녹화 경계 | 사건이 녹화 시작·끝에 걸려 전후가 물리적으로 없을 수 있다 | v4 `RequirementReport`는 이를 판정하지 않는다 | `recording` Owner(정철원)가 생성 실패/경고/사용자 고지와 span 정책을 결정. evidence는 미결을 닫지 않음 |
| I4 번호판·시각 관찰 전달 | **MVP에서 만들지 않는다(#280 · ADR-EVIDENCE-010).** `policy/requirement-rules-v6`에서 두 가시성 rule을 뺐고 adapter의 `mock_only` I4 값도 지웠다 | I4 미관찰은 FINAL_PACKAGE를 막지 않는다. 최종 영상 가시성은 판정하지 않는다 | 재도입은 readout `REPORT_VIDEO` 입력 계약 → case 배선 → 새 결정 순서(ADR-010 §8). `post_stamp_applied`는 별개로 recording transform provenance로 확인 |
| 실제 Consumer | 현재 `case` 공개 실행 구현은 골격이며 실제 projection 호출 경로가 없다 | Contract reader Mock까지만 입증 | 유소연이 실제 case 입력 경계/CaseView projection을 구현한 뒤 동일 artifact로 접합 확인 |

## 재현 명령과 검증 범위

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests/evidence -p 'test_*.py' -v
python -m daesingo.evidence.mock_integration
python -m ruff check src/daesingo/evidence tests/evidence
python -m compileall -q src/daesingo/evidence tests/evidence
python data/mock/validate_mock_pack.py
python scripts/check_contract_fixtures.py
python scripts/check_boundaries.py
git diff --check
```

2026-09-15 PR #58 후속 검증에서 evidence `46 tests OK`, Ruff `All checks passed`, compileall 성공을 확인했다. 공용 검증은 `46 JSON / 7 Scenario`, `structure 60 / JSON 26 / semantic 104 PASS`, boundary `0 violations`였고 `git diff --check`도 통과했다. null·빈 차량번호와 malformed RequirementReport, 평가하지 않은 자산 ref 교체 반례가 각각 validator/UNKNOWN/stable Package error로 차단되는 회귀 테스트를 포함한다. baseline 4종과 `run-summary.json`에는 `policy/requirement-rules-v3` 참조가 0건이며 평가 Report는 v4를 사용한다. 공용 validator PASS는 baseline 의미 정확성, 실제 Consumer E2E, AI/OCR 정확도, 외부 신고 성공, Owner 수락을 증명하지 않는다.

## 인수인계

유소연 `case` Consumer는 같은 `case_id`/`selection_rev`의 선택된 CandidateEvent, VisualEvidence, time/readout 입력, CorrectionRecord, IncidentClip/AssetFacts를 공개 함수에 전달하고 반환된 opaque refs를 그대로 저장·projection하면 된다. P의 `PLATE_REREAD`를 실제 `PLATE_READ` Job으로 바꾸고 stale Need를 제거하는 책임, `USER_REVIEWED` 판정, CaseView head 선택은 case에 남는다. evidence는 readout/runtime/export를 호출하지 않는다.

검토 시 우선 볼 파일은 `run-summary.json` → H/U baseline의 FINAL_PACKAGE와 Package → `requirement_rules_v4.json` → `test_policy_decisions.py` → `test_mock_integration.py` 순서다. H/U Package 복구는 남은 rule을 완화한 결과가 아니라 판정 주체가 없던 정확히 세 rule을 제거한 결과다. 실제 Runtime 준비 여부는 I4 관찰 배선과 `case` projection을 별도로 확인해야 한다.
