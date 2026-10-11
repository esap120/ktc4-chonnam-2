# 대신고 Dashcam·자율주행 Perception 기반 저비용 Coarse Candidate Generator — Research Import

기준일: 2026-08-25

상태: **Research — 구현·채택 결정 아님**

> 이 문서는 2026-08-25에 작성한 「대신고 Dashcam·자율주행 Perception 기반 저비용 Coarse Candidate Generator Deep Research Report」에서 현재 Search architecture 재검토에 직접 필요한 결론·pipeline·평가안을 이관한 팀용 연구 문서다. 원문 전체 보존본이 아니라 Search 의사결정에 필요한 부분을 정리한 이관본이다.

---

## 1. Executive Summary

**YES. 다만 세 위반유형을 하나의 CV 모델로 해결하려고 하면 안 된다.**

2026년 현재 자율주행·ADAS perception에서 이미 충분히 성숙한 기술을 조합하면, **중앙선 침범과 백색 실선 진로변경은 범용 VLM 없이도 고Recall Candidate Generator를 만들 가능성이 높다.** 반면 **신호위반은 traffic-light detection 자체보다 `어느 차량이 어느 신호를 따라야 하는가`가 어려워**, 순수 CV만 고집할 이유가 약하다.

권장 구조:

```text
사용자 기억 단서로 시간범위 축소
                │
        violation-type router
                │
      ┌─────────┼──────────┐
      │         │          │
   신호위반   중앙선침범   백색실선
      │         │          │
 CV scene gate │          │
      │         └────┬─────┘
      │         Lane + Vehicle
      │             + Track
      │             + Geometry
      ↓              ↓
Cheap VLM         Candidate
on gated clips       │
      └──────────┬───┘
                 ↓
          Candidate Union
                 ↓
          Strong Fine VLM
                 ↓
              Top-K
```

우선 challenger:

| 우선순위 | Challenger | 대상 | 학습 |
| --- | --- | --- | --- |
| **#1** | **CV_LANE_TRACK** | 중앙선 + 백색 실선 | 일단 없음 |
| **#2** | **TYPE_SPECIFIC_HYBRID** | 신호위반은 CV gate→VLM, 선 위반은 #1 | 일단 없음 |

첫 fine-tuning 후보는 위반 분류 모델보다 **한국 도로의 lane semantic(황색/백색 × 실선/점선)** 쪽이 더 직접적이다. 다만 pretrained perception이 실제 대신고 benchmark에서 부족하다고 확인되기 전에는 학습부터 시작하지 않는다.

---

## 2. 자율주행 perception에서 가져올 것과 가져오지 않을 것

이미 성숙한 primitive:

- vehicle detection
- lane geometry
- drivable area
- traffic-light detection/state
- multi-object tracking
- lane-change/cut-in recognition

대신고는 자율주행 제어가 아니라 **후보 생성**이 목적이므로 자율주행보다 permissive한 threshold를 쓸 수 있다.

반면 질문의 방향은 다르다.

```text
자율주행:
내 차가 어느 lane에 있는가?
내 차가 따라야 할 신호는 무엇인가?

대신고:
저 차가 어느 lane에 있는가?
저 차의 ground-contact point가 저 실선을 넘었는가?
저 차가 따라야 할 신호는 무엇인가?
그 신호가 적색일 때 저 차가 정지선을 넘었는가?
```

특히 신호위반은 `surrounding vehicle → lane → relevant traffic light` association이 필요하므로 중앙선/백색 실선과 같은 방식으로 묶지 않는다.

---

## 3. 중앙선·백색 실선 pipeline

### 3.1 중앙선 침범

```text
Video
 ↓
2 FPS lane perception
 ↓
황색 실선 / 이중실선 semantic
 ↓
5 FPS vehicle detection
 ↓
OC-SORT / ByteTrack
 ↓
vehicle ground-contact point
 ↓
local lane spline와 signed distance
 ↓
pre-side → crossing band → post-side
 ↓
candidate ±2~4 sec
```

bbox 중심보다 **bbox bottom-center**를 road-contact proxy로 쓴다.

각 frame에서:

```text
d_t = signed_distance(vehicle_footpoint, local_lane_curve)
```

를 계산하고,

```text
d_t < -margin
        ↓
 crossing band
        ↓
d_t > +margin
```

처럼 sign reversal이 일정 시간 지속되면 candidate를 만든다.

곡선도로 때문에 전체 차선을 Hough straight line 하나로 보는 방식은 피하고, target vehicle 근처의 local spline/tangent를 사용한다.

### 3.2 백색 실선 진로변경

중앙선과 동일한 stack을 공유하고 semantic filter만 다르게 둔다.

```text
CENTER_LINE:
  yellow + solid

SOLID_LANE_CHANGE:
  white + solid
```

단순 순간 교차는 camera/lane jitter를 많이 잡을 수 있으므로:

```text
line-side sign reversal
+
일정 lateral displacement
+
track persistence
```

를 함께 본다.

---

## 4. lane geometry와 lane semantic은 다른 문제다

범용 lane detector가 잘하는 것:

```text
여기에 lane boundary가 있다
```

대신고가 필요한 것:

```text
여기는 황색 중앙선이다
여기는 황색 이중실선이다
여기는 백색 실선이다
여기는 백색 점선이다
```

따라서 geometry가 충분한데도 제품 판단이 막힌다면 **semantic marking이 다음 병목**이 될 수 있다.

초기에는 pretrained geometry를 먼저 benchmark하고, 필요할 때만 한국 도로 lane-semantic adaptation을 검토한다.

---

## 5. 신호위반은 type-specific hybrid

쉬운 primitive:

```text
Traffic Light
Traffic Light State
Stop Line
Crosswalk
Vehicle
Intersection
```

어려운 relation:

```text
저 차량의 진행방향
        ↓
저 차량이 속한 lane
        ↓
그 lane을 통제하는 traffic light
        ↓
RED onset
        ↓
stop-line crossing temporal order
```

따라서 MVP에서는:

```text
전체 시간범위
 ↓
1~2 FPS cheap CV
 ↓
traffic light / intersection / stopline / RED 가능성 gate
 ↓
해당 ±수초만 higher-FPS / higher-res
 ↓
VLM relation verifier
```

처럼 CV를 violation judge보다 **VLM 호출 gate**로 쓰는 편이 현실적이다.

association이 애매하면 candidate 단계에서 버리지 말고 VLM으로 promote한다.

---

## 6. calibration / ego motion escalation

첫 challenger에 full calibration은 필요하지 않다.

```text
Level 0  lane-relative signed distance
Level 1  temporal lane smoothing
Level 2  background optical-flow homography stabilization
Level 3  IPM / calibrated BEV
Level 4  visual odometry / 3D
```

**Level 0부터 시작하고 failure-driven으로 올라간다.**

심한 slope, pitch 변화, 급커브, 좌우회전 false crossing, lane jitter가 반복될 때만 homography/BEV를 추가한다.

---

## 7. 후보 생성은 explainable evidence를 남긴다

단일 score보다 multi-signal union이 유리하다.

```text
CENTER_LINE candidates =
    line-side crossing
 OR very-low-distance-to-yellow-line + large lateral motion
 OR tracker discontinuity near yellow line
```

candidate schema도 score 하나보다 원인을 남긴다.

```json
{
  "start": 123.2,
  "end": 129.6,
  "violation_type": "CENTER_LINE",
  "generator": "CV_LANE_TRACK",
  "signals": {
    "line_type": "YELLOW_SOLID",
    "line_conf": 0.78,
    "track_conf": 0.91,
    "signed_distance_before": -12.4,
    "signed_distance_after": 18.7
  }
}
```

이 기록은 Fine prompt, 디버깅, false-negative 분석, UI 근거에 모두 활용할 수 있다.

---

## 8. Evaluation Protocol

Primitive benchmark와 제품 benchmark를 분리한다.

### Layer 1 — Primitive sanity

- vehicle recall
- lane recall
- line semantic recall
- traffic-light recall/state
- event-local track continuity

목적은 **왜 실패했는지**를 분해하는 것이다.

### Layer 2 — Candidate retrieval

Primary:

- Recall@3
- Recall@10

Secondary:

- Recall@30
- timestamp error
- false candidates/source-hour
- candidate minutes/source-hour

### Layer 3 — Efficiency

- wall-clock/source-hour
- GPU-sec/source-hour
- CPU-sec/source-hour
- RTF
- KRW/source-hour
- upload MB/source-hour
- VLM tokens/source-hour

### Layer 4 — E2E

모든 Coarse에 가능하면 **같은 Fine verifier**를 붙인다.

```text
VLM Cheap ─────┐
CV LaneTrack ──┼→ Same Fine → Final Recall@3
Other Coarse ──┘
```

---

## 9. 최소 실험 순서

### Experiment 0 — 학습 없이 primitive sanity

```text
pretrained lane
+ pretrained vehicle
+ tracker
```

를 실제 sample에 연결하고 황색/백색 선과 주변 차량을 실사용 가능한 수준으로 내놓는지 본다.

### Experiment 1 — CENTER/WHITE CV_LANE_TRACK

```text
A0
pretrained lane
+ pretrained vehicle
+ tracker
+ signed-crossing rule
```

```text
A1
A0
+ Korean lane-semantic adaptation
```

```text
A2
A1
+ stabilization/homography
```

**A2는 A1의 실패가 camera motion 때문일 때만 만든다.**

### Experiment 2 — RED

```text
R0: 전체 narrowed interval을 VLM
vs
R1: cheap CV gate → gated clips만 VLM
```

비교:

- gate recall
- gated-video %
- VLM input cost
- Final Recall@3

---

## 10. Benchmark 구성

AI-Hub event frames만으로 제품 의사결정을 하면 안 된다.

필수 구성:

```text
긴 정상주행
+
위반 사건
+
hard negatives
```

특히 필요한 hard negative:

- 실선 근처지만 crossing하지 않는 차량
- ego turn 때문에 움직여 보이는 차량
- lane detector가 흔들리는 frame
- 정상 점선 변경
- 빨간 신호지만 관련 없는 차량

실제 architecture 결정에는 주간/야간/우천/곡선/교차로/정체/카메라 차이도 포함해야 한다.

---

## 11. 지금 먼저 구현할 Challenger

### Challenger #1 — CV_LANE_TRACK

```text
FFmpeg decoder
        ↓
Lane perception
        │
        ├→ semantic marking
        │     yellow / white
        │     solid / dashed / double
        │
Vehicle detection
        ↓
OC-SORT / ByteTrack
        ↓
vehicle bottom-center
        ↓
local lane spline
        ↓
signed-distance history
        ↓
crossing rule + hysteresis
        ↓
temporal merge
        ↓
Top-K Candidate
```

이 challenger를 먼저 볼 이유:

1. 학습 없이 검증 가능
2. component가 작고 local 실행 가능
3. 구조가 explainable
4. 중앙선·백색 실선 두 유형을 함께 다룸
5. failure를 semantic / geometry / tracking으로 분해 가능
6. 실패하면 어떤 primitive만 보강할지 알 수 있음

### Challenger #2 — TYPE_SPECIFIC_HYBRID

```text
SIGNAL:
  traffic-light/intersection/stopline CV gate
  → VLM

CENTER_LINE:
  CV_LANE_TRACK

WHITE_SOLID:
  CV_LANE_TRACK
```

세 violation의 perceptual complexity가 다르므로 universal model로 통일하지 않는다.

---

## 12. 아직 먼저 만들지 않을 것

- 통합 end-to-end 교통위반 모델
- 2B~4B VLM fine-tuning
- full 3D lane topology
- HD-map 수준 lane↔signal association
- full visual odometry stack
- ReID-heavy MOT
- 세 violation universal classifier
- 대규모 corpus 무작정 재학습

benchmark가 더 단순한 구조로는 안 된다고 보여준 뒤에 escalation한다.

---

## 13. 최종 Architecture Recommendation

```text
                       User Memory
                            │
                      Time Narrowing
                            │
                     Violation Router
                            │
            ┌───────────────┼──────────────┐
            │               │              │
          SIGNAL         CENTER         WHITE_SOLID
            │               │              │
       CV Scene Gate        └──────┬───────┘
            │                      │
        Cheap VLM             Lane Semantics
            │                 + Vehicle Detect
            │                 + Local Tracking
            │                 + Crossing Rule
            │                      │
            └───────────────┬──────┘
                            │
                    Candidate Union
                            │
                       Temporal NMS
                            │
                         Top-K
                            │
                   Strong Fine VLM
```

핵심은 **Perception을 작은 VLM처럼 만들지 않는 것**이다.

```text
싼 곳에는 싸고 전문적인 CV
어려운 relation에는 VLM
```

을 사용한다.

---

## 14. 최종 추천

> 중앙선 침범·백색 실선은 `lane + vehicle + local tracking + image-space crossing` 기반 `CV_LANE_TRACK`을 VLM Coarse보다 먼저 실제 benchmark에서 비교할 가치가 충분하다. 신호위반은 이를 억지로 같은 구조에 넣지 말고 `cheap CV gate → VLM`의 type-specific hybrid로 별도 취급한다.

첫 실험에서 pretrained가 부족하다고 확인되기 전에는 fine-tuning하지 않는다.
