# cross-module contracts

여러 모듈이 함께 합의해야 하는 **canonical 데이터 계약**을 둔다.

- 팀 합의 전 초안은 각 module의 `contracts/`에서 작업할 수 있다.
- 합의된 계약은 이 폴더로 이동하고, 원래 module 폴더에 중복 사본을 남기지 않는다.
- 계약의 의미와 경계는 `architecture/module-architecture.md`를 따른다.
- 아직 합의되지 않은 필드를 빈칸 채우기 식으로 확정하지 않는다.
- 계약 1건은 `contract-<slug>.md`(현재 규칙)와 `adr/adr-<slug>.md`(확정 근거) 한 짝으로 둔다.
- 예외: `contract-http-api.md`(web ↔ api transport, §5-1 목록 밖)는 [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247) 결정대로 처음부터 이 폴더에서 Draft로 작성했고, 2026-10-05 web · case · recording 리뷰를 거쳐 `http-api/v1` `Final — Accepted`가 됐다. 짝 ADR `adr/adr-http-api.md`는 Accepted다. 아래 「16건 모두 Final」은 data contract 집계라 이 transport 계약은 들지 않는다.

## 감사 후속 상태 (2026-09-08 snapshot · 2026-09-19 maintenance)

2026-09-08 종결 ADR은 **당시 closure snapshot과 결정 근거**다. 현재 계약 상태는 이 폴더의 `contract-*.md`를 먼저 본다. 2026-09-19 기준 canonical 계약 16건은 모두 `Final — Accepted`다. 그 이전 회차는 [접합부 종결 ADR (2026-09-07)](adr/adr-data-contract-call-closure-2026-09-07.md), 보정·철회 기록은 [후속 보정 ADR (2026-09-06)](adr/adr-consistency-followup-2026-09-06.md), 원래 지적은 [계약 정합성 외부 감사](../../management/contract-consistency-audit-2026-09-06.md)에 있다.

- Owner 결정으로 종결·검증된 접합: B01·B02(CaseView 값 상태·요건) · B03·B05(판독 결과↔ReadoutRun↔UsageRecord, 재판독 발주·`usage_refs` 지위 포함) · B06(`SpanResolution` `failure`·`OUT_OF_TIMELINE_RANGE`·`MissingRange.source_ref`, `span-resolution/v1.2`) · **B07**(자산 사실 — 아래) · B08(`AnalysisScope` relative range, `analysis-scope/1.1.0`) · B09(사용 timeline revision).
- **`Final — Accepted`로 전환(2026-09-08):** recording 자산 계약 2건 `contract-source-asset-media-stream.md`(`source-asset-media-stream/v1`) · `contract-analysis-source-derived.md`(`analysis-source-derived/v1`). 4 Consumer(search·readout·case·evidence) Review가 종결되고 필수 조건이 반영됐다. 짝 ADR 2건도 `Accepted`이고 Consumer Review 기록은 각 짝 ADR §7이 소유한다. **자산 계층 `ContractRef.kind` 값 공간은 `contract-source-asset-media-stream.md` §2.1 한 곳이 소유한다**(소문자 snake_case, 정확 문자열 비교).
- 같은 날 함께 닫힌 접합: `MissingRange.source_ref`가 `ContractRef | null`(키 항상 존재) · **`AssetSpan`에 identity를 추가하지 않고** 사건 구간 canonical ref를 `incident_clip`으로 단일화(readout `span_ref` 삭제 → `plate-readout/v1.2`·`overlay-time-readout/v1.2`, `EvidenceNeeds` §8.3 참조 대상 확정).
- **2026-09-08 snapshot:** 열린 결정 회차는 없었고 BLOCK 12건은 전부 종결됐다. 당시 W04(`JobExecution` 소비자 확인·domain `PARTIAL`↔runtime `status`)와 N02(`CorrectionRecord` Draft Review·readout taxonomy·eval 정답지)가 `PENDING_OWNER`로 남아 있었다.
- **2026-09-10 이후 후속:** N02 중 `CorrectionRecord` Consumer Review는 완료되어 `correction-record/v1.1`이 `Final — Accepted`로 승격됐고, readout failure taxonomy도 후속 문서/Mock에 반영됐다. `JobExecution` W04의 소비자 확인은 `contract-job-execution.md` §11에 여전히 명시적으로 남아 있으므로 여기서 임의 종결하지 않는다. eval의 locked test/정답지 운영 잔여는 eval 문서가 소유한다.
- 따라서 **09-08 ADR의 `CONTRACT_AUDIT_PARTIAL`/준비도 표시는 그 시점의 감사 판정으로 보존**하고, 현재 계약의 Final/Draft 여부를 판단하는 표로 재사용하지 않는다.

계약 예시의 의미 검증은 `../../../scripts/check_contract_fixtures.py`(fixture: `fixtures/call-closure-2026-09-07/` · `fixtures/call-closure-2026-09-08/`, 검사 V0~V15)가 한다. 경계·헤더 검사는 `check_boundaries.py`와 별개다.
