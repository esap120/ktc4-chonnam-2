# case/decisions

조사·실험을 근거로 확정한 이 모듈 내부 결정을 둔다. 다른 모듈/제품 범위를 침범하는 결정은 여기서 단독 확정하지 않는다.

## 현재 결정

- `timeout-fallback.md — timeout 담당·결정 시점 (A-1)`
- `correction-log-reuse.md — correction 로그 재사용 전제·익명화 3줄 (C-4)`
- `budget-krw-normalization.md — 예산(KRW) vs 비용(USD) 통화 정규화, Mock 기본값 (P3-1, 이슈 #19)`
- `candidate-stale-revision-display.md — CaseView.candidates[].timeline_revision/stale_revision 필드 신설 (P1-10, 이슈 #18 위임)`
- `generic-warn-package-and-situation-response.md — situation_confirmation·unconfirmed_fields 신설, EVIDENCE/FINAL_PACKAGE WARN→READY 투영 (이슈 #25 A절·댓글)`
- `eval-round2-ground-truth-and-usage.md — plate_reread_001·unknown_abstain_partial_001 참값 라벨 확정, STALE attempt UsageRecord 컨벤션 (이슈 #22 B-3·B-4)`
- `orchestration-service-layer.md — service.py/ModuleAdapter Protocol 도입 + Mock→Real 교체(W5/W6) 진행 기록 (RealAdapter 실측 real 교체 범위, case.get_view() 진입점)`
- `intent-llm-eval-target-thresholds.md — intent LLM 평가 목표치(schema_compliance/field_accuracy/hallucination/missed rate) 딥리서치 기반 1차 설정 (2026-09-19 실측 완료, 3개 후보 전부 통과 — §4)`
- `intent-llm-model-selection.md — 자연어 단서 구조화 LLM 최종 채택 Gemini 3.8 Flash(2026-09-22 재검토로 GPT-5 Nano에서 변경, §10) — §1~§9는 첫 결정 기록으로 보존. 2026-10-05 단일 점수(정확도 × 일관성)로 확정, §13. 2026-10-06 GPT-6 Luna · reasoning effort challenger 검증 — 기본값 유지, 비용 대안을 Luna `none`으로 교체, §14`
- `agent-framework-adoption-criteria.md — LangGraph/Google ADK 등 agent framework를 지금 도입하지 않는다는 결정 + 재검토 트리거 4개`
- `input-fingerprint-implementation-label-deferred.md — input_fingerprint의 implementation label 조합 로직을 지금 만들지 않는다는 결정 + 재검토 트리거 2개 (이슈 #77)`
- `intent-hint-robustness-policy.md — 도메인 밖 입력은 스키마 변경 없이 null/low로 처리, 모순 정보는 마지막 값+confidence low 채택 (PM 재검토, 2026-09-22)`
- `reselect-observation-reuse.md — 다른 후보를 골랐다가 돌아오면(A→B→A) 같은 탐색 결과 안에서는 관찰(Fine·판독)을 재사용, 후보 목록이 바뀌면 버림 (W7 7순위, 2026-09-30)`
- `command-appended-job-records.md — command가 이번에 append한 JobRecord를 응답 body 밖으로 돌려준다(`execute_command()` → `CommandResult`), handle_command는 response만 (W7 8순위 8-7, 2026-10-05)`
- `empty-case-and-manifest.md — 빈 case 생성(`create_case()`, case가 `case_` + uuid4 발급) · adapter 없는 등록 · 업로드마다 `manifest_summary` 갱신(file/ok 수만, duration·range·failed는 계산 안 함, case_rev 유지, INTAKE 전용) (W7 8순위 8-12, 2026-10-05)`
- `case-store-mysql.md — CaseStore MySQL 영속화 1단계: 하이브리드 schema(cases + append-only 레코드 3종) · 호출자 transaction 참여 · FOR UPDATE/FOR SHARE · opt-in MySQL 테스트 (W7 8순위 8-6, 2026-10-05). adapter 제거는 2단계`
- `running-jobs-derivation.md — running_jobs를 case가 JobRecord 정산 기록(REFLECTED · STOPPED_WAITING · CANCELLED · SUPERSEDED, state JSON)으로 계산, 실행 기록 없으면 PENDING, 공개 함수의 running_jobs 인자 제거 (W7 8순위 8-11, 2026-10-06)`
- `start-analysis.md — 분석 시작(START_ANALYSIS): case당 타임라인 하나를 교체 가능한 port로 받고(임시로 등록 순서대로 이어 붙임), 탐지 유형 4개 전부 · 예산 150초/설정 1,000원 · 첫 fingerprint sha256 · 단서 구조화 대기 90초 (W7 8순위 8-1, 2026-10-07)`
- `jobexecution-read-port.md — JobExecution read port를 `CaseStore(executions=…)`로 주입, case가 자기 job_id로 조회해 running_jobs · Fine 실행 상태를 계산, 진입 함수의 job_executions · visual_verify_status 인자 제거 (W7 8순위 8-10, 2026-10-11)`
- `stop-analysis.md — 분석 중단(STOP_ANALYSIS): SEARCHING에서 기다리던 HINT_EXTRACT · COARSE_SEARCH만 CANCELLED로 정산하고 cancelled_job_ids로 돌려줌(Runtime cancel은 composition root), stage는 SEARCHING 유지 · coarse_search PARTIAL · case.analysis_stopped notice, 늦은 결과는 「기다리는 job만 받는다」 (W7 8순위 8-9, 2026-10-11)`
- `result-reflection.md — Worker T2 반영 진입점 reflect_execution(): case 행 잠금 → 처리한 execution_id(state JSON processed_executions)면 ALREADY_APPLIED → 기다리지 않는 job이면 NOT_APPLIED(정산 사유) → kind별 반영(HINT_EXTRACT · COARSE_SEARCH, 내용은 주입 ProducedReader), 반영기 없는 kind는 오류 (W7 8순위 8-8, 2026-10-11)`
- `observation-storage.md — 8-6 2단계: search · readout 결과는 common/runtime 결과 저장소(T1 같은 tx, 해석 없는 append-only — RT-10 Implementer 확인 대기), evidence는 get_view마다 재계산, ModuleAdapter는 남기고 무상태 StoredObservationAdapter를 CaseStore adapter_factory로 주입, 선택 관찰은 현재 후보 세대 · candidate_id로 거름(6.6순위 조건 2), T2 관찰 kind는 정산 + READY gate (W7 8순위 8-6, 2026-10-12)`
- `real-e2e-scenarios.md — real 경로를 Mock 5개 시나리오로 확장(infra는 비동기 E2E 몫 · rebase는 범위 밖), 관련 asset은 선택 IncidentClip과 그 lineage로 고름(select_case_assets, 역할로는 안 거름), 재판독은 readout-native-hires, 대조는 case fixture 마지막 CaseView · 발견 사항 4건 (W7 4 · 5순위, 2026-10-12)`
- `report-video-export.md — 신고용 영상: 신고 상황 응답 뒤 case가 REPORT_VIDEO_EXPORT 자동 발주(배선은 recording export handler 뒤로 보류), case.report_video_not_generated는 응답 뒤 영상이 없는 동안 계속 붙이고 GENERATE_REPORT_VIDEO는 이전 발주가 있고 실행 중이 아닐 때만, 첫 발주를 버튼으로 받지 않음 (#351, 2026-10-13)`
