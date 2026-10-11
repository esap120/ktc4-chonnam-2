# Retrieval Coarse v2 — 「선에 걸친 장면」 문장 · 4fps · 정상 문장 대비

작성일: 2026-10-11. 상태: **완료 — 신호 부족(Recall@3 2/11, 무작위 95백분위 4 이하). 차선 표시 프레임 점검(§6)도 통과하지 못함**. [#279](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/279) 실험 B의 후속이다. 로컬 RTX 3060에서만 실행하며 유료 API 호출·운영 코드 변경·모델 학습은 없다.

**사후 설계다.** [v1](retrieval-coarse-preflight-2026-10-11.md)의 set1 결과를 본 뒤 문장과 점수 방식을 바꿨다. 같은 set1로 다시 재므로 결과가 좋아져도 set1에 맞춘 효과일 수 있다. 판단은 v1과 같은 기준으로 하되, 정식 성능 근거로 쓰려면 다른 데이터에서 다시 확인해야 한다.

## 1. v1에서 바꾼 것과 이유

| 항목 | v1 | v2 | 이유 |
| --- | --- | --- | --- |
| 문장 | 유형마다 1개, 「선을 넘는다」(동작) | 유형마다 3개, 「선 위에 걸쳐 있다」(상태). 3문장 임베딩 평균 후 정규화 | 모델이 사진 한 장만 본다. 동작보다 한 장에 보이는 상태가 맞다. 여러 문구 평균으로 문구 하나의 영향을 줄인다 |
| 점수 | 위반 문장 유사도 | **위반 문장 유사도 − 정상 문장 유사도** | v1에서 C10·C44는 세 유형 최고점이 같은 프레임이었다. 문장과 무관하게 눈에 띄는 장면의 효과를 빼려는 것 |
| 프레임 | 2fps | **4fps** | 선에 걸친 순간이 짧아 놓치지 않도록 |
| 평활 | 3프레임(1.5초) | **5프레임**(1.25초, 4fps에서 1.5초에 가장 가까운 홀수) | 시간 폭을 v1과 비슷하게 유지 |

나머지(모델 `google/siglip-so400m-patch14-384` fp16, 첫 영상 스트림, 384² 전처리, 유형별 13클립 전체 z-score, [t−2, t+2] 4초 후보, 유형당 최대 5개, 순위, 채점기, 기준선, 판단 기준)는 v1 §3–§5와 같다. 차선 위반 문장의 주체는 앞차로 한정했다. 촬영 차량이 선을 넘는 사건은 이 문장으로 잡지 않는다.

## 2. 문장 (실행 전 고정)

**실선 차로변경 (`SOLID_LINE_LANE_CHANGE`)**
1. a dashcam photo of a car straddling a solid white lane line, half in one lane and half in the next
2. a car ahead driving on top of a solid white lane line between two lanes
3. a vehicle halfway across a continuous white line on the road

**중앙선 침범 (`CENTER_LINE_CROSSING`)**
1. a dashcam photo of a car straddling the yellow center line, half in the opposite lane
2. a car driving on top of the double yellow center line
3. a vehicle halfway across the center line into oncoming traffic

**신호위반 (`SIGNAL`)**
1. a dashcam photo of a car in the middle of an intersection while the traffic light is red
2. a car crossing the stop line under a red traffic light
3. a vehicle driving through a crosswalk at a red light

**정상 주행 (대비용, 세 유형 공통)**
1. a dashcam photo of cars driving normally within their lanes
2. a car ahead driving in the middle of its lane
3. an ordinary road scene with traffic staying in lane

## 3. 판단 기준

v1 §5와 같다. 판단용 3유형 Recall@3이 무작위 95백분위를 넘고 5/11 이상이면 A, 무작위 95백분위만 넘으면 약한 신호, 넘지 못하면 신호 부족이다. v1(4/11)과의 차이는 11사건·1회라 1–2건이면 우연과 구분하지 않는다.

## 4. 한계

v1 §6에 더해:

- 사후 설계라 set1에 맞춘 효과와 실제 개선을 구분할 수 없다.
- 문장·점수·fps를 한꺼번에 바꿔 어느 변경이 효과를 냈는지 분리하지 않는다.
- 정상 문장을 세 유형에 공통으로 빼므로, 신호위반처럼 차선과 무관한 유형에는 대비가 덜 맞을 수 있다.

## 5. 결과 (2026-10-11 실행)

실행: 13클립 2,480프레임(4fps) × 문장 12개, 1회. 누락 클립 0. 합계 111.2초(모델 로드 제외), 피크 VRAM 1.97GiB. 로컬 `.omc/retrieval/runs/sims_v2.jsonl`, 채점 `runs/score_v2.json`.

| 조건 | Recall@1 | **Recall@3** | Recall@5 | 전체 후보 겹침 | 무작위 Recall@3 평균 / 95백분위 / P(≥관측) | 순위 섞기 95백분위 |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| **v2 3유형 — 판단용** | 0/11 | **2/11** | 4/11 | 5/11 | 2.36 / 4 / 0.79 | 3 |
| v2 정답 유형 — 참고 | 0/11 | 3/11 | 5/11 | 5/11 | 3.64 / 6 / 0.78 | 5 |
| 참고: v1 3유형 | 3/11 | 4/11 | 6/11 | 8/11 | 1.30 / 3 / 0.019 | 4 |

사건별 첫 적중 순위(v2 3유형): C05 20–22s 2 · C33 3 · C00 5 · C08 5 · C44 8, 나머지 6건 없음.

**판단: 신호 부족.** 판단용 Recall@3 2/11은 무작위 위치 95백분위(4) 이하다. v1에서 rank1이던 신호위반 C08·C33도 순위가 내려갔다(5위·3위).

### 진단 — 정상 문장 대비를 뺀 경우 (판단에 쓰지 않음)

같은 v2 임베딩에서 정상 문장을 빼지 않고 위반 문장 유사도만으로 다시 채점했다. 새 실행은 없다(`runs/score_v2_rawdiag.json`).

- 3유형 Recall@3 4/11, 무작위 95백분위 4 이하(P=0.12). 적중은 v1과 거의 같다(C08·C33 rank1, C44 2위, C10 3위).
- 즉 v2 성적 하락은 주로 **정상 문장 대비** 때문이다. 문장 변경·4fps만으로는 v1보다 나아지지 않았다.

13클립 전체 프레임에서 위반 문장 유사도와 정상 문장 유사도의 상관:

| 유형 | 상관 |
| --- | ---: |
| 실선 「선에 걸친 차」 | 0.935 |
| 중앙선 「선에 걸친 차」 | 0.959 |
| 신호위반 | 0.577 |

차선 문장은 정상 주행 문장과 상관이 0.94–0.96이다. **이 모델은 블랙박스 프레임에서 「선에 걸친 차」와 「차로 안에서 정상 주행하는 차」를 거의 같은 장면으로 본다.** 두 점수를 빼면 남는 것이 대부분 잡음이라 순위가 무작위에 가까워졌다. 신호위반은 상관이 낮아 문장 자체에 구분 정보가 있지만, 같은 정상 문장을 빼면서 그 정보도 약해졌다.

### 해석

- 프레임 한 장 + 범용 이미지·문장 모델로는 차선 위반을 정상 주행과 구분하지 못한다. 문장을 「상태」로 바꿔도 마찬가지다.
- 신호위반은 v1·v2 진단 모두에서 rank1이 나왔다. 적신호가 프레임에 보이는 장면을 찾는 용도로만 신호가 있다.
- 이 경로로 차선 위반 Coarse를 더 다듬기보다, 차선 위반은 CV_LANE_TRACK(차량·차선 좌표로 교차를 직접 계산)에 맡기는 편이 맞다고 본다. 신호위반만 retrieval로 후보를 좁히는 안은 새 데이터에서 따로 확인해야 한다.

## 6. 추가 점검 — 차선 표시 프레임 (2026-10-12)

v2 뒤에 「PP-LiteSeg 차선 표시 영상을 넣고 문장을 그에 맞추면 구분되는가」를 작게 확인했다. 조건과 통과 기준은 실행 전에 스크립트(`.omc/retrieval/overlay_check.py`)에 고정했다.

- 입력: 실선 6클립(C05·C09·C39·C47·C10·C44)의 기존 PP-LiteSeg 표시 프레임 120장씩(원본 2fps, 초록=solid). 범례 글자가 있는 상단 66px은 잘라냈다.
- 사건 프레임 38장(정답 구간 안), 먼 프레임 557장(모든 정답 구간에서 5초 이상).
- 점수: sim(「a car on top of a green line」) − sim(「a car between green lines」). 참고로 같은 시각 원본 프레임에 「white lane line」 문장 쌍.
- 통과 기준: 표시 프레임 대비 AUC ≥ 0.70 그리고 원본 참고보다 높음.

| 점수 | AUC (0.5 = 구분 못 함) |
| --- | ---: |
| **표시 프레임 · 「초록선 위」 − 「초록선 사이」 (판단용)** | **0.44** |
| 원본 프레임 · 「흰 선 위」 − 「흰 선 사이」 (참고) | 0.51 |
| 표시 프레임 · 「초록선 위」 단독 (보조) | 0.70 |

클립마다 대비 점수가 가장 높은 프레임이 정답 구간 안에 든 경우는 0/6이다.

**판단: 통과하지 못함.** 차선 표시를 넣어도 「선 위의 차」와 「선 사이의 차」를 가르지 못한다. 이 경로(v3)는 진행하지 않는다.

관찰(판단에 쓰지 않음): 「초록선 위」 문장 단독은 AUC 0.70이었다. 대비를 빼면 사라지므로, 차가 선 위에 있는지가 아니라 초록 실선이 많이 보이는 장면인지에 반응한 것으로 본다.
