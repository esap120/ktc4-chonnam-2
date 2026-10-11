# recording

**Owner:** 정철원

이 폴더는 `recording` 모듈의 세부 문서 작업공간이다. authoritative 경계는 `docs/architecture/module-architecture.md`, 역할은 `docs/management/ownership.md`를 따른다.

## 다루는 범위

- 원본 파일과 시간축
- 파일 경계 해결
- 파일이 주는 시각 후보
- GPS 좌표
- 분석용/외부/신고용 사본과 보관·삭제

## 다루지 않는 범위

- 교통위반 의미 판단
- 신고요건
- AI 모델·프롬프트
- 어느 시각 출처가 최종적으로 맞는지 판정
## 문서 운영

- `research/`: 조사·비교·Spike
- `experiments/`: 실제 설정/입력/결과/learning
- `decisions/`: 조사·실험 후 확정한 module 내부 결정
- `contracts/`: 이 모듈이 생산/소비하는 계약의 초안·검토 메모. cross-module 최종 계약은 `architecture/contracts/`로 승격

## 1차 구현 기준

- [recording 1차 Mock E2E Tech Spec](decisions/first-integration-tech-spec.md)

빈 spec을 미리 만들지 않는다. 필요해질 때 Owner가 생성한다.

## 실제 원본 capability

- [실제 영상 처리 Edge Case 목록](real-video-edge-cases.md)
- [로컬 원본의 실제 FrameRef·PNG 조회](local-frame-access.md)
- [등록 원본의 현재 AssetFacts 조회](local-asset-facts.md)
- [실제 단일 원본의 SpanResolution 계산](local-span-resolution.md)
- [실행별 로컬 AnalysisSource materialization](local-analysis-source.md)
- [실제 단일 VIDEO IncidentClip과 Readout 경계](local-incident-clip.md)
