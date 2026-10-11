# `evidence` — 증거 확정 / 신고 정책 / Package

**Owner:** 김준영 (`docs/management/ownership.md`) · **경계:** `docs/architecture/module-architecture.md` §4-모듈4 · **문서 작업공간:** `docs/modules/evidence/`

## 이 폴더가 하는 일 (요약 — 원문은 §4-모듈4)

Observation → confirmed Evidence·Timestamp 최종 resolution·사용자 correction 적용·`EvidenceNeeds`·Visual Event → Report Type 매핑·신고 요건 검사(PASS/WARN/BLOCK)·신고문 Template·`ReportPackage`·handoff

## 이 폴더가 알면 안 되는 것 (§4-모듈4 「알면 안 되는 것」)

AI model/prompt / OCR library / ffmpeg / Worker lease·heartbeat / 사용자가 어느 화면에 있는지 / 외부 시스템에 직접 작업 발주. **순수 함수 모듈** — 다른 도메인 모듈을 호출하지 않는다

## 공개 함수

`daesingo.evidence`는 Final Contract 값을 받거나 반환하는 순수 함수 경계다. 인수는 Contract JSON을 역직렬화한 `dict`이며, `scenario_id`나 Mock 파일명은 공개 입력이 아니다.

- `resolve_time(...) -> TimeResolution`
- `classify_visual_evidence(visual_evidence, situation_response=None) -> VisualEvidenceDisposition`: `EvidenceRecord` 조립 이전에 VisualEvidence 하나의 결말을 정한다(`ASSEMBLE` / `AWAIT_SITUATION_RESPONSE` / `NOT_ASSEMBLED`). `verification=NOT_OBSERVED`는 예외가 아니라 안정적인 비조립 결과다 — 후보 선택·순회는 여기 없다.
- `resolve_independent_facts(*, case_id, selection_rev, time_resolution, plate_readout, location_hint=None, gps_observation=None, correction_records=None) -> dict`: EvidenceRecord의 **상황 독립 필드** `occurred_at` · `vehicle_number` · `location`만 계산한다(#239). 각 값은 EvidenceRecord의 같은 필드와 모양이 같고, 결정할 수 없으면 키를 두지 않는다. 해당 필드의 CorrectionRecord도 같은 규칙으로 반영한다. **EvidenceRecord 생성 API가 아니다.** `record_ref` · `basis` · `event` · `provenance` · `situation_response`가 없고, RequirementReport · ReportPackage로 이어지지 않는다. Fine `UNCERTAIN` 응답 대기(`AWAIT_SITUATION_RESPONSE`)에서도 부를 수 있다. case가 이 결과로 `record_id=null` 부분 투영을 만든다. 응답 전에 최종 Record를 만들지 않는다는 원칙(ADR-EVIDENCE-009 §2.1)은 그대로다. 시각은 `resolve_time()`이 만든 `TimeResolution`을 받는다.
- `assemble_evidence(...) -> EvidenceRecord`: 위 세 필드는 `resolve_independent_facts()`와 같은 계산으로 채운다. 그래서 응답 전 부분 투영과 응답 후 Record가 같은 규칙을 따른다.
- `calculate_evidence_needs(...) -> EvidenceNeeds | None`
- `evaluate_requirements(evidence_record, *, scope, report_id, evaluated_at, time_resolution, asset_facts=(), observation_facts=None, supersedes_id=None) -> RequirementReport`
- `build_report_package(...) -> ReportPackage`
- `render_report(...) -> dict`: `safety-report-policy/v1.2`의 결정론적 renderer. specific은 `CONFIRMED`/`CORRECTED`, generic은 `USER_UNSURE`를 명시해야 하며 위치가 없으면 장소 슬롯 없는 template을, `vehicle_number=None`이면 차량번호 슬롯 없는 template을 고른다. 번호판 없는 신고문이 허용되는지는 호출자가 정한다.
- `correction_heads(...) -> dict`: evidence가 소비하는 CorrectionRecord chain head 검증
- `validate_contract(contract) -> list[str]`: 다섯 출력 Contract의 최소 경계 검사

`evaluate_requirements`의 rule 목록은 호출자가 전달하지 않고 활성 catalog가 선택한다. `time_resolution`은 시각 표시 조건부 rule selector이며, `observation_facts`는 사후 각인(`post_stamp_applied`)의 upstream 관찰을 명시적으로 주입하는 Python 호출 인수다(최종 영상 번호판·시각 표시 관찰은 v6에서 읽지 않는다 — ADR-EVIDENCE-010). 둘 다 새 Runtime wire schema가 아니다. `PackageNotReady`는 ready-only Package가 발행되지 않았음을 나타내며 Contract에 새 status를 추가하지 않는다. `VisualEventNotAssembled`는 `assemble_evidence()`가 `NOT_OBSERVED`로 직접 호출됐을 때 가짜 Record 대신 멈추는 경계이며, producer 계약 위반이 아니라 호출자가 분류를 건너뛴 경우다(`ADR-EVIDENCE-007`).

## 정책 데이터

- `attachment_policy_v1.json` — K1의 decimal byte 용량 상한과 첨부 개수 상한, outcome 매핑.
- `deadline_policy_v1.json` — K2의 2개 달력일 계산, 결과 매핑, 2026·2027 대한민국 공휴일 snapshot. 외부 공휴일 API를 사용하지 않는다.
- `requirement_rules_v2.json` — K3에서 채택됐으나 D1 반영으로 첫 실행 전에 대체된 보존 revision. 수정하거나 활성화하지 않는다.
- `requirement_rules_v3.json` — D1 반영 후 실제 실행됐으나 ADR-EVIDENCE-005 D2로 대체된 보존 revision. 수정하거나 활성화하지 않는다.
- `requirement_rules_v4.json` — ADR-EVIDENCE-005 D2로 사건 장면·전후 상황 세 rule을 제거한 revision. 실제 실행됐으나 ADR-EVIDENCE-008(#172 D-3)로 대체된 보존 revision. 수정하거나 활성화하지 않는다.
- `requirement_rules_v5.json` — ADR-EVIDENCE-008(#172 D-3)의 revision. 실제 실행됐으나 ADR-EVIDENCE-010(#280)으로 대체된 보존 revision. 수정하거나 활성화하지 않는다. `EVIDENCE` 기본 4개, `FINAL_PACKAGE` 무조건 12개와 시각 표시 조건부 3개 중 정확히 1개를 선택했다. v4에서 번호판 두 rule만 바꿨다 — `evidence.vehicle_number.present`는 값이 없을 때 `PlateReadout` 존재 여부로 `WARN`(판독 후 못 읽음)/`UNKNOWN`(판독 결과 없음·실행 실패)을 나누고, `package.vehicle.plate_visible_in_report_video`의 관찰 `false`는 `BLOCK` → `WARN`이다. `package.report.content_length`에는 번호판 없는 렌더 mode 두 개(`*_without_plate`, `plate_readout_performed` 필수)를 더했고, 신고문 policy는 `safety-report-policy/v1.2`를 참조한다. 나머지는 v4에서 그대로 계승한다.
- `requirement_rules_v6.json` — **활성 catalog.** `EVIDENCE` 기본 4개, `FINAL_PACKAGE` 무조건 11개와 시각 표시 4갈래 중 정확히 1갈래를 선택한다. v5에서 최종 신고용 영상 재관찰(I4) rule 두 개만 뺐다 — `package.vehicle.plate_visible_in_report_video`를 무조건 목록에서 지웠고, `OK` · `time.verified_overlay_already_present` 갈래는 선택되지만 rule을 추가하지 않는다(`no_rule`, 이전 `package.time.overlay_visible`). 따라서 `observation_facts`의 `plate_visible_in_report_video` · `time_overlay_visible`은 읽지 않는다. 나머지는 v5에서 그대로 계승한다(ADR-EVIDENCE-010).
- `safety_report_policy_v1_1.json` — 위치 유무에 따른 네 deterministic template과 신고유형 매핑. v1.2로 대체된 보존 revision.
- `safety_report_policy_v1_2.json` — **활성 신고문 policy.** v1.1의 네 template을 그대로 두고, 판독 후 번호판을 식별하지 못한 경우의 차량번호 슬롯 없는 네 template을 더했다(`docs/modules/evidence/decisions/safety-report-policy-v1.2.md`).

활성 requirement catalog 선택점은 `policy_catalog.py`의 `_ACTIVE_REQUIREMENT_CATALOG_FILE` 한 곳이며 현재 `requirement_rules_v6.json`이다. 출력 `policy_ref`는 이 파일에서 읽는다.

번호판 판독을 수행했지만 식별하지 못한 기록은 번호판 없는 신고문으로 `ReportPackage`(`report-package/v1.2`, `vehicle_number=null`)가 발행된다. 판독 결과 자체가 없는 기록(실행 실패)은 렌더 입력이 불완전해 Package가 없다. 두 경우를 가르는 판별은 `requirements.py`의 `_plate_readout_performed()` 한 곳이다(ADR-EVIDENCE-008 §6).

loader는 각 정책의 식별자·필수 구조·공휴일 coverage·catalog rule 구성을 검증한다. 깨진 구성은 `PolicyConfigurationError`로 정상 `RequirementReport` 발행 전에 중단하고, 관찰 사실 부족은 check의 `UNKNOWN`으로 남긴다.

## 재현

저장소 루트의 PowerShell에서 실행한다.

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests/evidence -p 'test_*.py'
python -m daesingo.evidence.mock_integration
```

두 번째 명령은 공용 H/U/P/R upstream JSON을 로딩하되 실제 baseline 순수 함수를 호출하고, 결과를 `docs/modules/evidence/artifacts/first-completion/`에 기록한다. 이 adapter와 그 Consumer reader는 테스트 도구이며 실제 `case` projection이 아니다.

## 상태

**ADR-EVIDENCE-002(K1~K4)·003(D1)·005(D2)·008(#172 D-3) 정책 엔진 반영 완료.** 공용 H/U Mock에서 각각 `PASS`·`WARN` FINAL_PACKAGE와 Package 발행을 확인했다. 다만 번호판·시각 관찰은 여전히 `mock_only` 입력이므로 실제 Runtime의 I4 배선, 실제 영상 생성, `case`의 CaseView projection과 외부 제출은 포함하지 않는다. 현재 검증 범위와 후속 항목은 [`first-completion-result.md`](../../../docs/modules/evidence/first-completion-result.md)를 따른다.
