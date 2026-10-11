# evidence 구현 ADR

이 폴더는 `evidence` Owner가 내린 결정과 그 이유를 기록한다. 내부 구현 구조(ADR-001·004), 모듈이 단독으로 정할 수 있는 정책(ADR-002·005·008), 그리고 `evidence`가 Contract Owner인 계약의 개정 결정(ADR-003)이 여기 들어간다.

- **다른 모듈의 Owner 경계는 바꾸지 않는다.** 다른 Owner의 입출력 계약이 걸리면 이 폴더에서 단독 확정하지 않고 해당 Owner와 별도로 검토한다.
- **계약·정책의 본문은 여기가 아니다.** 규범 원문은 `docs/architecture/contracts/`와 `../decisions/`가 소유하고, 이 폴더는 왜 그렇게 정했는지를 남긴다. 둘이 어긋나면 원문이 이긴다.
- 미결 계약이나 정책을 구현 편의를 위해 확정하지 않는다.

## 목록

- [ADR-EVIDENCE-001 — Final Contract 기반 1차 Mock 통합 구현 구조](adr-first-mock-integration-implementation.md)
- [ADR-EVIDENCE-002 — 1차 완료 후 Owner 정책 결정 K1-K4](adr-first-completion-owner-decisions.md) — K1·K2·K3·K4 accepted
- [ADR-EVIDENCE-003 — 위치를 확보하지 못한 사건의 `ReportPackage` 발행 (D1)](adr-location-absent-package.md) — accepted. 이슈 #48 종결, ADR-002 §5.6·§5.8·§5.11·§5.14 갱신
- [ADR-EVIDENCE-004 — versioned requirement policy engine 구현 구조](adr-requirement-policy-engine.md) — K1~K4·D1 loader/evaluator/template/error 경계 구현 구조
- [ADR-EVIDENCE-005 — 판정 주체가 없는 사건 장면·전후 상황 rule 제거 (D2)](adr-event-context-rules-removal.md) — accepted. `FINAL_PACKAGE` 무조건 rule 15 → 12, ADR-002 §5.6·§5.12·§5.14·§5.15 갱신
- [ADR-EVIDENCE-006 — 번호판 형식 규칙은 hard reject가 아니라 사용자 검토 신호로 사용](adr-license-plate-format-review-rules.md) — accepted, implementation pending. PR #80 실측 + PR #88 공식 규정 조사 연결, 후속 versioned rule 구현 필요
- [ADR-EVIDENCE-007 — `NOT_OBSERVED` VisualEvidence는 `EvidenceRecord` 이전에 끝나는 정상 결과 (D3)](adr-not-observed-non-assembly.md) — accepted. 이슈 #137, `classify_visual_evidence()` 경계 신설, `contract-evidence-record-needs.md` null 예외 절 명확화(버전 유지)
- [ADR-EVIDENCE-008 — 번호판 식별 실패와 실행 실패의 Requirement 경계 (#172 D·D-2·D-3)](adr-plate-identification-failure-boundary.md) — accepted. 활성 catalog `policy/requirement-rules-v5` 발행, ADR-002 §5.4·§5.6 · ADR-005 §5.5 번호판 행 대체. 번호판 없는 Package의 입력 계약·template은 후속
- [ADR-EVIDENCE-009 — 상황 응답 전 진행 범위와 사라진 사건 확인 단계 (#171 B·B-2)](adr-situation-response-timing.md) — accepted. ADR-005 §2.5·§5.4 재검토, rule catalog 변경 없음
- [ADR-EVIDENCE-010 — 최종 신고용 영상 재관찰(I4) 가시성 rule 제거 (#280)](adr-i4-report-video-visibility-rules-removal.md) — accepted. 활성 catalog `policy/requirement-rules-v6` 발행, `FINAL_PACKAGE` 무조건 rule 12 → 11, 검증된 overlay 시각 갈래는 rule 없음. ADR-002 §5.6·§5.7 · ADR-005 §5.5·§5.7 · ADR-008 §5.2·§6.2·§8 대체 표시
