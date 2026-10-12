# 차선·차량 관계 기반 프레임/ROI 선별: 문서 확인과 모델 후보

작성·원문 확인일: 2026-10-05

상태: **Research — 채택·구현 결정 아님. 이번 작업에서는 새 모델 추론이나 VLM API 평가를 실행하지 않았다.**

## 1. 문서화 여부

사용자가 제공한 「2025–2026 차선 인식 기반 프레임·ROI 선별과 VLM 검증 연구 조사」의 동일 제목 및 LKAlert, DiffusionLane, SC-Lane, HSDF-Lane, HORNet, HiMu, DriveMRP 이름은 작업 전 저장소 검색에서 발견되지 않았다. 확인 범위는 현재 로컬 저장소이며 Notion·외부 문서의 부재까지 뜻하지 않는다.

관련 방향은 이미 다음 문서에 있다.

- [CV 적용 방향](./cv-application-strategy-research-2026-10-01.md): 화면 좌표 대신 차선 대비 차량 횡위치 측정, CV 단독 측정 → Fine 보강 → 후보 union.
- [YOLO 보조 Fine 조사](./yolo-assisted-gemini-fine-research-2026-09-16.md): 차량 추적·차선 결합과 CV-first challenger.
- [적응적 샘플링 조사](./adaptive-video-sampling-research-2026-09-29.md), [오버레이 조사](./visual-prompting-overlay-research-2026-10-01.md): 프레임 선택과 시각 증거 보강.

제공 원문은 별도 텍스트(`lane-roi-vlm-user-source-2026-10-05.txt`, 로컬 보관·저장소 미게시)에 그대로 보존했다. 이 파일은 사용자 제공 자료이며, 전체 주장·논문 순위가 검증됐다는 뜻이 아니다. 아래는 프로젝트 선택에 필요한 핵심 수치와 적용성을 공식 논문·저장소 및 기존 실험 기록으로 재확인한 결과다.

## 2. 성능 수치를 먼저 구분해야 한다

**F1 97.59%는 “우리 영상의 위반을 97.59% 확률로 맞힌다”는 뜻이 아니다.** F1은 precision과 recall의 조화평균이며, 데이터셋·정답 정의·평가 임계값에 종속된다. 모델 confidence/softmax도 별도 보정과 검증 없이 위반 존재 확률로 해석할 수 없다.

| 질문 | 확인 결과 | 의미·제한 |
| --- | --- | --- |
| 제공 목록에서 차선 위치 검출의 가장 높은 대표 수치는? | DiffusionLane ResNet101, **LLAMAS F1 97.59%** | 해당 차선 벤치마크 결과. 다른 데이터셋과 순위 비교 불가 |
| DiffusionLane의 CULane 성능은? | MobileNetV4-Hybrid-M, **F1 81.32%** | 동일 모델 계열도 데이터셋·backbone에 따라 수치가 다름 |
| 같은 CULane에서 당장 공개 가중치로 비교할 후보는? | CLRerNet⋆ DLA34, **논문 5개 seed 평균 F1 81.43±0.14%**, 공개 EMA 가중치 **81.55%** | 평균과 단일 가중치 결과를 구분. DiffusionLane보다 모든 조건에서 우월하다는 뜻은 아님 |
| 외부 lane mask를 VLM에 넣는 직접 사례는? | LKAlert Qwen2.5-VL-7B: **Accuracy 69.80%, Precision 78.02%, Recall 46.71%, F1 58.63%** | LoRA 학습 후 LKA 실패 예측. 실선 위반 검출률이 아님 |
| 제공 자료의 motion-risk VLM 대표 결과는? | DriveMRP-Agent: **합성 Accuracy 88.03%, 실제 데이터 Accuracy 68.50%** | 다른 과제·데이터. LKAlert와 직접 순위 비교 불가 |

수치 근거: [DiffusionLane 논문 Tables 3–5](https://arxiv.org/html/2510.22236v1), [CLRerNet 공식 성능·가중치](https://github.com/hirotomusiker/CLRerNet#performance), [LKAlert Tables I–II](https://arxiv.org/html/2505.11535v1), [DriveMRP 논문](https://arxiv.org/html/2507.02948v3).

제공 원문의 근접 연구에 나오는 clear-condition 99.6%는 위반 검증이나 CV→VLM 체인의 성능으로 확인된 수치가 아니다. 이번 선정의 최고 모델 근거로 사용하지 않았다. 이 조사는 세계 전체 모델의 SOTA 순위를 확정하는 전수 조사도 아니다.

## 3. 우리 프로젝트에서 이미 측정한 결과

| 기존 실험 | 표본·조건 | 관측 결과 | 해석 |
| --- | --- | --- | --- |
| sol 이미지 Coarse + Fine 720p | 7클립, 위반 4건 × 3회 | **8/12 = 66.7%**, 정상 3클립 × 3회 오탐 0 | 해당 작은 표본의 사건 구간 중첩 HIT. 모든 HIT의 대상 차량 GT를 확인한 것은 아님 |
| 같은 sol 조건, 새 set1 | 10클립, 위반 11건 × 3회 | **3/33 = 9.1%** | Coarse가 정답 시간대 후보를 자주 누락. 음성 클립 없음 |
| AI Hub 공간 모델 후보 + sol Fine | 15클립, 사건 13건, 1회 | **2/13 = 15.4%** | 정답 종류·구간 중첩 판정. 정확한 위반 차량 recall 아님 |
| AI Hub LRCN 후보 + sol Fine | 같은 15클립, 사건 13건, 1회 | **4/13 = 30.8%** | 앞선 공간 후보 방식보다 높았지만 Fine 검사 범위·힌트·신호 기준도 변경됨 |
| 두 AI Hub 조합을 set1에 한정 | 같은 10클립·11사건 | 공간 **1/11 = 9.1%**, LRCN **2/11 = 18.2%** | 영상 범위는 같지만 프롬프트·후보·반복 수가 달라 통제 비교 아님 |

근거: [10/02 sol Fine 720p](../experiments/search-v3-gpt-sol-fine720-2026-10-02.md), [10/04 sol set1](../experiments/search-v3-gpt-sol-fine720-set1-2026-10-04.md), [AI Hub 공간 후보 + sol](../experiments/aihub-coarse-sol-fine-2026-10-04.md), [AI Hub LRCN 후보 + sol](../experiments/aihub-lrcn-sol-fine-2026-10-04.md).

**기존 작은 표본의 최고 관측치는 66.7%지만 일반 성공 확률은 아직 알 수 없다.** 15클립 AI Hub 비교에서는 LRCN 조합의 30.8%가 더 높았다. 서로 다른 표본의 66.7%와 30.8%를 모델 순위로 비교하지 않는다.

[AI Hub 모델 단독 실측](../experiments/aihub-model-video-2026-10-04.md)에서 LRCN의 83.3%(10/12)는 위반이 있다는 조건에서 종류를 맞힌 비율이다. 정상 3클립에도 위반 클래스를 반환했으며 softmax는 0.998/0.987/0.872였다. 위반 존재 확률로 쓰면 안 된다.

## 4. 적용 가능한 모델 후보

### 4.1 새로운 차선 geometry 비교: CLRerNet⋆ DLA34 우선

[공식 저장소](https://github.com/hirotomusiker/CLRerNet)에 Apache-2.0 코드, 추론 예제, 학습 가중치 다운로드가 명시되어 있다. 공개 EMA 가중치의 CULane F1은 81.55%이며, 차선 위치·confidence를 차량 추적과 연결하는 비교 후보로 적합하다. 설치는 공식 mmdetection 3.3 환경 또는 Docker가 권장된다. 실제 Windows·RTX 3060 호환성과 프로젝트 영상 성능은 이번에 실행하지 않았다.

- 가중치: [clrernet_culane_dla34_ema.pth](https://github.com/hirotomusiker/CLRerNet/releases/download/v0.1.0/clrernet_culane_dla34_ema.pth)
- 실선/점선·색상·법적 중앙선 역할을 모두 제공하는 모델로 취급하지 않는다.
- 2025–2026 신모델은 아니지만, 사용자는 신규 공개 모델만 쓰라는 제약을 두지 않았으므로 실용 대조군에 포함한다.

### 4.2 제공 목록의 최신 2D 고성능 후보: DiffusionLane

[공식 UnLanedet](https://github.com/zkyntu/UnLanedet)은 2025-11-17 코드 공개와 Apache-2.0을 명시한다. 2D 차선 곡선 출력은 현재 블랙박스 입력에 연결하기 쉽다. 다만 이번에 확인한 [공식 Model Zoo](https://github.com/zkyntu/UnLanedet/blob/main/doc/model_zpp.md)에는 DiffusionLane 가중치 행이 없었다. **코드 공개와 최고 성능 checkpoint 확보를 구분한다.** 최고 backbone의 가중치를 확보하거나 학습 조건을 재현하기 전에는 즉시 적용 가능한 최고 모델로 확정하지 않는다.

실선/점선·흰색/황색·중앙선 의미를 갖춘 추론 출력은 확인되지 않았다. 그런 기능은 VLM 또는 별도 semantic 모델과 평가가 필요하다. [논문](https://arxiv.org/html/2510.22236v1).

### 4.3 배포·속도 비교군: UFLDv2 ResNet34

[공식 저장소](https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2)에 MIT 코드, CULane/TuSimple/CurveLanes 사전학습 가중치, ONNX 변환·TensorRT 영상 추론 안내가 있다. 공식 CULane ResNet34 F1은 **76.0%**다. CLRerNet보다 해당 차선 성능 수치가 낮지만, 실행·내보내기 경로가 있어 차선 상대위치 측정의 초기 대조군으로 적합하다. FPS는 같은 하드웨어에서 직접 측정해야 한다.

### 4.4 이미 있는 한국 도로 모델: 새로 찾기 전에 재사용 기준을 둔다

프로젝트는 AI Hub 71555의 **Mask R-CNN R50-FPN**을 이미 실행했다. 백색 실선, 황색 실선/이중실선, 정지선을 각각 내며 차량 YOLOv5도 준비되어 있다. [실측 보고서](../experiments/aihub-model-video-2026-10-04.md).

백색 선 모델은 점선 경계를 `white_solid` **0.99**로 오분류했다. 황색 연석도 황색 선으로 탐지했다. 따라서 기존 마스크는 차선 주변 ROI와 위치의 보조 근거로 쓰되, 실선 여부·중앙선 역할의 정답으로 쓰지 않는다. 현재 코드 `scripts/aihub_hybrid_candidates.py`는 화면상 차량 이동과 마스크 근접성을 본다. **동일 경계에 대한 부호 거리의 전후 변화와 ego-motion 보정을 검증한 crossing detector는 아니다.** 새 차선 모델만 교체해 이 문제가 해결된다고 가정하지 않는다.

별개인 [AI Hub 197 차선/횡단보도 데이터](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=197)는 FCN ResNet50 **F1 0.8972**와 실선/점선·색상 라벨을 명시한다. 이 수치는 71555 모델의 성능이 아니다. 데이터 라벨의 존재만으로 배포 모델이 모든 속성을 추론 출력한다고 단정하지 않는다. 모델 파일 구성·속성별 평가·가중치 이용조건은 추가 확인 대상이다.

### 4.5 3D 모델과 학습형 VLM은 연구 후보

[SC-Lane](https://arxiv.org/abs/2508.10411)의 OpenLane F-score는 64.3%다. [HSDF-Lane](https://arxiv.org/abs/2606.31172)은 도로 높이와 lane-existence prior를 사용한다. 경사·3D 좌표가 필수일 때 검토하되, OpenLane 3D 결과를 CULane 2D 결과와 직접 비교하지 않는다. HSDF의 semantic prior도 실선·황색·중앙선 분류라는 뜻은 아니다. Depth3DLane의 상세 가중치·출력·성능은 이번 보충 조사에서 재검증하지 않았다.

LKAlert·DriveMRP의 Qwen2.5-VL 결과는 과제 학습을 포함한다. 공개 base Qwen에 마스크/궤적을 넣기만 하면 논문 성능이 재현된다고 주장하지 않는다. 지금은 Fine 입력 증거를 구성하는 참고로 활용하는 편이 타당하다.

## 5. 프레임 선별과 VLM 입력의 권고

다음은 문헌과 기존 실패에서 도출한 **적용 제안**이며, 프로젝트에서 성능이 입증된 새 파이프라인이 아니다.

```text
기존 Coarse 후보 + 별도 CV 후보(비교 실험)
→ 동일 차량·동일 경계 추적, 카메라 움직임을 고려한 상대 위치
→ 교차 전 / 교차 중 / 교차 후 프레임 묶음
→ 원본 full frame + 차량과 경계가 함께 들어가는 ROI
→ 기존 Fine VLM에서 원본 증거 확인
```

1. 첫 비교는 CLRerNet⋆·UFLDv2·기존 AI Hub 마스크의 lane-relative trajectory다. `141927` 양성과 `141956` 합법 점선 변경을 함께 본다. 점선 변경도 기하학적 crossing은 있어야 하며, 위반 종류 판정과 분리한다.
2. 후보 구간의 전·중·후 상태를 보존한다. 선이 가장 잘 보이는 프레임만 고르면 차량이 선을 가리는 교차 순간을 잃을 수 있다. 가림·추적 실패 시 원본 구간의 균일 샘플을 유지한다.
3. camera calibration이나 신뢰할 수 있는 3D 복원 없이 픽셀 거리를 미터로 표기하지 않는다. 비교 가능한 차선 상대 좌표·정규화 거리부터 사용한다.
4. overlay는 추정치임을 표시하고 원본을 함께 준다. 실선·노란색·중앙선 라벨을 정답처럼 그리지 않는다. 이미 확인한 마스크 오분류에 VLM이 따라가는지도 평가한다.
5. 기존 Coarse가 놓친 사건은 Coarse 뒤의 선별만으로 회복할 수 없다. 후보 보강 비교에서는 기존 후보와 CV 후보를 합치는 조건을 따로 두고, CV로 기존 후보를 삭제하는 hard filter는 사건 보존 검증 이후에 판단한다.

문헌 근거와 한계:

- [LKAlert](https://arxiv.org/html/2505.11535v1): RGB+lane mask+CAN을 VLM에 전달. guided는 unguided보다 정확도 +2.10%p, F1 +2.70%p지만 속도는 4.60→1.97 samples/s(RTX 5090). runtime 프레임 필터 실증은 아니다.
- [DriveMRP](https://arxiv.org/html/2507.02948v3): 전방·BEV·궤적 projection이 결합된 motion-risk 학습. 우리 프로젝트의 위반 검증 정확도나 overlay 단독 효과는 아니다.
- [HORNet](https://arxiv.org/html/2603.18850v1): NExT-QA 동일 4프레임에서 71.50% vs uniform 64.24%; VideoMME 8프레임 설정은 baseline 대비 16.2%p 하락. 시간 증거 보존이 중요하며 성능 수치를 교통위반으로 이전하지 않는다.
- [HiMu](https://arxiv.org/html/2603.18558v2): SEQ·RIGHT_AFTER로 순서·인접성을 다룬다. 4.63초/1.88초 selector 수치는 8-GPU RTX 6000 Pro 조건이므로 로컬 속도로 인용하지 않는다.
- [TAU-R1](https://arxiv.org/abs/2603.19098): 도로 CCTV anomaly 이해와 coarse classifier→reasoner 구조. 우리 이동 블랙박스의 실선 교차 chain 검증과 다르다.
- [Attention steering](https://arxiv.org/abs/2608.17095): detector-localized visual token의 내부 attention 변경. 원문은 더 안전한 판단을 입증하지 않으며, 상용 VLM API에서 같은 조작을 할 수 있다고 가정하지 않는다.

## 6. 다음 평가에서 답해야 할 것

같은 영상·정답·Fine 모델/프롬프트·입력 해상도·반복 수를 고정하고 uniform / CV-selected / full+ROI / original+overlay를 비교한다. 후보 생성 변경과 Fine 프롬프트 변경의 효과를 분리한다.

- **사건 보존:** 전·중·후 증거가 모두 남은 사건 비율, 필터 때문에 새로 누락된 사건 수.
- **최종 판정:** 실선·중앙선 별 precision/recall/F1, 대상 차량 일치, 사건 시각 일치. 정상 영상과 양성 영상 안의 정상 구간도 포함한다.
- **실선·색 의미:** 점선·연석·황색 실선·이중선 오분류를 별도로 센다. geometry 성능과 분리한다.
- **비용:** 후보 수·중복 호출·이미지 수·토큰·지연·CV 처리시간·GPU 메모리. 확정 요율이 없으면 금액을 만들지 않는다.

이 단계의 연구 선택은 **CLRerNet⋆를 새로운 geometry 대조군으로 우선 검토하고, UFLDv2와 기존 AI Hub 모델을 비교하며, DiffusionLane은 최고 조건 checkpoint 확보 후 비교**하는 것이다. 우리 영상에서 최고 성공 확률이 나오는 모델은 동일 조건의 평가 전에는 확정할 수 없다.
