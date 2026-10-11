# CV_LANE_TRACK 우선순위 재검토 — Coarse 병목 기준

작성일: 2026-10-06

상태: **Research / priority review — 구현·채택 결정 아님**

관련:

- [Dashcam·자율주행 Perception 기반 Coarse 연구](./dashcam-perception-coarse-candidate-research-2026-08-25.md)
- [기존 CV 적용 방향](./cv-application-strategy-research-2026-10-01.md)
- [set1 Sol Fine720 결과](../experiments/search-v3-gpt-sol-fine720-set1-2026-10-04.md)
- [challenger 정책](../decisions/challenger-policy.md)
- #279 — Retrieval baseline · VideoChat3 local preflight

---

## 1. 왜 다시 보는가

10/01 CV 전략은 `CV 단독 측정 → Fine 힌트 → CV 후보 생성기` 순서를 두고, CV candidate generator를 가장 뒤에 뒀다.

하지만 10/04 set1 평가에서 현재 최고 Fine 조건을 유지했는데도:

- 10 clips / 11 violation events
- 3 repeats
- GT와 겹친 Coarse candidate: **4 / 33**
- final detection: **1 · 1 · 1 / 11**

이 확인됐다.

현재 병목은 Fine model을 더 강하게 만드는 문제보다 **사건 구간 자체를 Coarse가 회수하지 못하는 문제**에 더 가깝다.

중앙선 침범과 백색 실선 진로변경은 `vehicle + lane + local track + crossing geometry`로 분해 가능한 explicit geometry-heavy task이므로, Retrieval / Video MLLM보다 먼저 작은 CV baseline을 확인할 정보 가치가 커졌다.

---

## 2. 재검토한 우선순위

현재 권고 순서:

```text
P0  CV_LANE_TRACK
    lane + vehicle + local tracking + crossing geometry

P1  Retrieval Coarse
    embedding similarity → Top-K interval

P2  VideoChat3 preflight
    video-native temporal reasoning
```

이 순서는 #279를 폐기한다는 뜻이 아니다.

CV_LANE_TRACK이 충분한 recall을 내지 못하거나, CV로 분해하기 어려운 `SEARCH_FAILURE`가 계속 남으면 #279의 Retrieval / VideoChat3 실험을 이어간다.

---

## 3. 왜 CV_LANE_TRACK을 먼저 보는가

- 현재 주요 실패 유형인 중앙선·백색 실선에 직접 대응한다.
- pretrained component 조합으로 학습 없이 minimum viability를 볼 수 있다.
- 긴 영상을 local에서 반복 scan하기 상대적으로 가볍다.
- `lane / semantic / tracking / geometry`로 failure를 분해할 수 있다.
- 결과가 실패해도 다음 보강 지점을 구체적으로 알 수 있다.
- stronger VLM/GPU 환경을 요청하기 전에 더 싼 구조가 어디까지 되는지 확인할 수 있다.

목표는 CV가 위반을 최종 판정하는 것이 아니다.

> **긴 영상에서 법적으로 중요한 lane boundary를 차량이 교차한 시점을 높은 Recall로 회수할 수 있는가?**

를 먼저 본다.

---

## 4. Prior implementation reference — 보고보고 Incident Ops

공개 레퍼런스:

https://github.com/flosure23/bogobogo-incident-ops

보고보고에서는 다음 흐름을 실제 CV/Eventization 검증 pipeline으로 운영했다.

```text
YOLO detector
 ↓
ByteTrack
 ↓
trajectory
 ↓
geometry / ROI / line relation
 ↓
event rule
 ↓
structured artifact
 ↓
annotated video
 ↓
FP / FN human review
 ↓
ADR / next experiment
```

참고 경로:

```text
docs/04_evaluation/eventization_yolo_validation/
apps/backend/app/services/detection/yolo_bytetrack.py
apps/backend/app/services/eventization/geometry.py
scripts/eval/visualize_selected_validation_eventization.py
eventization/
```

대신고에서는 고정 CCTV의 static ROI/tripwire를 그대로 재사용하지 않는다.

```text
보고보고:
fixed line + tracked trajectory → crossing

대신고:
frame별 lane spline + tracked vehicle road-contact point
→ lane-relative signed distance → crossing
```

즉 **실험 운영 방식과 artifact/failure-review 구조를 참고하고, geometry는 dashcam 환경에 맞게 새로 설계**한다.

---

## 5. 10/06 로컬 feasibility probe

별도 정식 experiment가 아닌 로컬 진단 probe도 수행했다.

- pretrained vehicle + tracker + lane location + image-space crossing
- 작은 현재 개발셋에서 기존 VLM Coarse가 놓친 일부 중앙선/실선 사건의 차량·시각을 CV가 회수하는 사례를 확인
- RX 6800 DirectML 경로에서 source 643초를 약 151초에 처리하는 실행 가능성을 확인

다만 이 probe는 **성능 주장 근거로 사용하지 않는다.**

이유:

- ranking / 판정 규칙 일부가 동일 데이터 관찰 후 정해짐
- held-out validation 없음
- 장시간 정상주행 및 충분한 hard negative 없음
- 일부 사건은 위반 차량 GT가 불명확
- 정식 eval scorer가 아닌 근사 채점 포함
- 새 Fine 입력/질문 변경까지 함께 들어간 진단 조건이 존재

따라서 현재 의미는 다음 한 줄로 제한한다.

> **CV_LANE_TRACK을 정식으로 사전고정·held-out 평가할 가치가 있다는 feasibility signal이 추가됐다.**

probe의 원본 overlay/video는 개인정보·영상 재배포 권리 검토 전이므로 이 PR에 포함하지 않는다.

---

## 6. 정식 실험에서 지킬 것

보고보고 방식처럼 구현보다 먼저 평가 구조를 고정한다.

```text
Step 0  dataset / environment readiness
Step 1  lane primitive sanity
Step 2  vehicle detection / tracking sanity
Step 3  lane-relative crossing geometry
Step 4  annotated-video failure review
Step 5  Candidate Recall@K
Step 6  FP/FN taxonomy
Step 7  architecture decision
```

최소 측정:

- Recall@1 / @3 / @5 또는 현재 eval SSOT와 맞춘 Recall@K
- GT ↔ candidate interval overlap
- candidate 0 비율
- false candidates / negative clip 또는 source-hour
- candidate duration budget
- lane semantic error
- event-local track continuity
- crossing geometry error
- wall-clock / source-video-hour
- peak VRAM / 실행 backend

규칙·threshold·ranking은 held-out 실행 전에 문서/코드로 고정한다.

---

## 7. 시각화 artifact 원칙

CV 실험에서는 JSON metric만으로 판단하지 않고 annotated video를 만든다.

최소 overlay:

- vehicle bbox / track ID
- trajectory
- vehicle bottom-center
- lane spline / lane semantic
- signed distance
- crossing state
- candidate interval

다만 공유용 artifact는 로컬 debug와 분리한다.

```text
viz/
  debug/        # GT 표시 가능, 로컬 전용
  reviewer/     # GT 비노출, 필요한 비식별화 적용
  publication/  # 공개/재배포 권리 확인 사례만
```

번호판·얼굴 등 식별 정보와 외부 영상 재배포 가능 여부를 확인하기 전에는 원본 overlay MP4/JPG를 저장소에 올리지 않는다.

---

## 8. 신호위반은 별도

신호위반은 중앙선/실선과 같은 CV-only 구조로 통일하지 않는다.

```text
CV scene / primitive gate
 ↓
candidate clip
 ↓
VLM relation verifier
```

`target vehicle ↔ lane ↔ relevant traffic light` association이 핵심 난점이므로 `TYPE_SPECIFIC_HYBRID`를 유지한다.

---

## 9. 이 문서가 결정하지 않는 것

- 운영 Gemini/VLM Coarse 제거
- CV candidate generator production 채택
- #279 종료
- Retrieval / VideoChat3 실험 폐기
- GPU 요청 취소
- 특정 detector/lane/tracker 최종 채택
- CV만으로 위반 확정

실제 challenger 개방은 기존 challenger 정책을 따른다.
