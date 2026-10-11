# search/research

외부 자료, 비교 조사, 기술 Spike를 둔다. 조사 결과 자체는 결정이 아니다.

- `gemini-baseline-research-2026-08-27.md` — Gemini baseline 실측 착수용 자료조사 **원문** (출처 링크 포함, 결정 아님)
- `architecture-input-memo.md` — 위 원자료를 요약·가공해 v4 작성 근거가 된 Owner 메모 (결정 아님)
- `yolo-assisted-gemini-fine-research-2026-09-16.md` — YOLO 객체 추적 근거와 사전학습 CV-first 후보 생성기를 현재 VLM-first baseline과 비교하고, Fine A/B 및 P0~P3 병렬 candidate 실험·조건부 전환 기준을 정리한 조사 (2026-09-17 갱신, 결정 아님)
- `dashcam-perception-coarse-candidate-research-2026-08-25.md` — 자율주행·ADAS perception을 대신고 Coarse에 적용하는 조사 이관본. 중앙선/백색 실선은 `lane + vehicle + local tracking + image-space crossing`, 신호위반은 `CV gate → VLM`의 type-specific hybrid를 우선 제안 (결정 아님)
- `cv-application-strategy-research-2026-10-01.md` — crop×힌트 결과(대상 연결은 고쳐지나 검출 0) 이후 CV 적용 0~3단계안(차선 대비 횡위치 측정 우선), Ultralytics 제공 범위, 차선 모델·AI Hub 학습 모델(FCN ResNet50, 실선/점선)·라벨링 규모, 승인·통보 경로 정리 (결정 아님)
- `cv-lane-track-priority-review-2026-10-06.md` — 10/04 set1의 Coarse overlap 4/33을 반영해 CV_LANE_TRACK을 Retrieval/VideoChat3보다 먼저 정식 검증할 것을 제안. 공개 `bogobogo-incident-ops`의 detector→tracker→geometry→overlay/failure-review workflow를 참고하고, 10/06 로컬 probe는 feasibility signal로만 기록 (결정 아님)
- `adaptive-video-sampling-research-2026-09-29.md` — 적응적 프레임 선택·공간 초점·조기 종료·Cerberus 등 긴 영상 Coarse→Fine 연구를 프록시 제약 아래 적용성으로 정리한 조사 (수치 원문 대조 전, 결정 아님)
- `visual-prompting-overlay-research-2026-10-01.md` — SoM·ViP-LLaVA·FGVP 시각 프롬프팅(오버레이) 효과·설계 지침, 경량 차량/차선 CV 후보 비교, 사례 A·B 오버레이 A/B 실험안 (수치 원문 대조 전, 결정 아님)
- `traffic-violation-video-research-2025-2026-2026-10-02.md` — 2025–2026 교통위반 판정(DashCop·UAV 등)·교통 VLM(RoadSafe365)·긴 영상 grounding(ExtremeWhenBench·TrafficRAG) 조사를 현재 Coarse→Fine 구조에 대응시키고, 고정 참고 사례 Fine A/B 등 쓸 지점과 안 쓸 지점을 정리 (수치 원문 대조 전, 결정 아님)
