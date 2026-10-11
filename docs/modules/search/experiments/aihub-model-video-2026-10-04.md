# 다운로드한 AI Hub 모델 9종의 실제 영상 평가

2026-10-04 · 로컬 진단 실험 · 제품 파이프라인 변경 없음

**결론: 차선·차량·신호등을 관찰하는 보조 모델로 활용할 가능성이 있다. 현재 가중치만으로 위반 여부를 자동 확정하기는 어렵다.** LRCN은 정상 클래스가 없고, 차선 모델은 점선을 실선으로 높은 확신으로 탐지한 사례가 있다. 후보 차량을 추적하고 차선·신호등을 연결하는 단계가 추가로 필요하다.

수치 원문: `aihub-model-video-2026-10-04-results.json` (로컬 보관). 재실행 코드: `scripts/aihub_model_video_{data,adapters,infer,lrcn,score}.py`.

## 1. 실제로 확인한 모델 구성

입력 경로: `C:/Users/User/Downloads/교통법규 위반 상황 데이터/AI모델`.

| 가중치 | 실제 모델·출력 | 활용 후보 |
|---|---|---|
| `위반상황분류.h5` | CNN + LSTM, 25×64×64 BGR 입력, 신호 / 중앙선 / 진로변경 3클래스 | 짧은 구간의 장면 유형 힌트 |
| `model_객체탐지_신호위반.pt` | YOLOv5: car, red/yellow/green/left_signal | 차량·신호등 위치와 색 |
| `model_객체탐지_중앙선침범.pt` | YOLOv5: car | 차량 위치 |
| `model_객체탐지_진로변경.pt` | YOLOv5: car, tunnel_light | 차량 위치·터널 맥락 |
| `model_객체탐지_안전모.pt` | YOLOv5: no_helmet, helmet, motorcycle, no_helmet_motorcycle | 이륜차·머리 후보 |
| `model_차선탐지_신호위반.pth` | Mask R-CNN R50-FPN: 정지선 | 정지선 주변 영역 |
| `model_차선탐지_중앙선침범.pth` | 같은 구조: 황색 실선 / 황색 이중실선 | 중앙선 후보 영역 |
| `model_차선탐지_진로변경.pth` | 같은 구조: 백색 실선 | 차선 후보 영역 |
| `model_교통영역탐지.pth` | 같은 구조: 횡단보도 / 교차로 | 교차로 공간 맥락 |

객체탐지 모델의 파일명에 위반명이 있어도 실제 출력은 차량·신호등 등이다. 위반 차량과 정상 차량을 구분하는 클래스는 없다. 안전모 모델은 속성 클래스를 따로 갖는다.

차선 노트북은 폴리라인을 `LineString.buffer(20.0)`으로 넓혀 마스크 학습에 사용한다. 이중선은 `buffer(40.0)`이다. 따라서 출력 마스크는 차선 중심선 자체가 아니다. 근거: `1.모델소스코드/4.차선 탐지 폴리라인 탐지/detectron2_교통영역_차선.ipynb` cell 15, 43, 49, 54. LRCN 입력·클래스 순서는 분류 노트북 cell 4, 12, 27과 가중치 shape를 함께 확인했다. YOLO 클래스는 가중치의 `model.names`에서 직접 읽었다.

배포본의 라이선스 파일 첫머리는 LRCN·Detectron2 계열 Apache 2.0, 객체탐지 계열 AGPL v3다. 이번 실행에 사용한 YOLOv5 v7.0 소스의 표기는 GPL v3다. 이것은 다운로드 파일에 적힌 내용을 확인한 것이며, 데이터 이용조건이나 제품 배포 허가를 확정한 것은 아니다.

## 2. 영상·평가 조건

- `src/daesingo/search/video/`의 15개 영상, 총 **645.658초**.
- 같은 폴더 `정답지.md`의 사람 / set1_g3 라벨: 위반 영상 12개, 정상 영상 3개, 위반 사건 13건. 신호 2건, 중앙선 2건, 실선 진로변경 9건이다.
- 공간 모델마다 동일한 **651프레임**을 1fps로 추출했다. 8개 모델 합계 **5,208프레임 추론**. source frame index / source fps로 실제 시각을 기록하고 JPEG quality 95로 캐시했다.
- LRCN은 BGR·64×64·255 정규화를 원본 노트북과 맞췄다. 전체 영상에서 균등한 25프레임, 정답 사건 주변에서 25프레임, 5초 창 / 2.5초 이동의 세 방법을 실행했다. 시퀀스 캐시는 5fps다.
- 원본 학습 프레임의 시간 간격은 제공 노트북에서 규정하지 않는다. 영상의 5fps·균등 추출은 이번 실험의 적용 방식이며 원래 학습 입력과 시간 밀도가 같다는 보장은 없다.
- GPU: RTX 3060 12GB. Python 3.10.20, PyTorch 2.5.1+cu121, torchvision 0.20.1+cu121. LRCN은 TensorFlow 2.15.1 CPU 실행.
- YOLO: longest side 640, stride에 맞춘 letterbox, RGB, NMS IoU 0.45. Mask R-CNN: BGR, short edge 800 / max 1333, 원본 R50-FPN 설정, 모든 가중치 `strict=True` 로드.
- 공간 모델은 confidence 0.25로 실행하고 저장된 동일 결과에서 0.25 / 0.5 / 0.8을 비교했다. 원본 차선 추론 예시의 0.8도 포함한다.
- 각 공간 모델 3프레임 워밍업 후 CUDA 동기화로 지연을 측정했다. 표의 속도는 전처리·모델·후처리·CPU 결과 변환·마스크 RLE 인코딩을 포함하고, 영상 디코드·캐시 이미지 읽기·오버레이 저장·모델 로딩은 제외한다. 전체 서비스 FPS가 아니다.

영상·가중치·정답지 해시, 클래스, 모델 소스 revision, 원본 프레임 시각은 JSON 및 로컬 manifest에 기록했다. 이 15개는 작은 개발 진단 표본이며 학습 데이터와의 중복 여부를 검증한 공식 test split은 아니다. 정밀 bbox·mask·대상 차량 정답이 없으므로 mAP, mask IoU, 위반 차량 위치 정확도는 계산하지 않았다. 안전모 사건 라벨도 없으므로 해당 정확도는 측정하지 못했다.

## 3. LRCN: 종류 분류는 일부 가능하지만 정상 배제가 실패한다

| 평가 | 결과 | 해석 |
|---|---:|---|
| 전체 영상 25프레임, 위반 영상의 종류 | **10/12 = 83.3%** | 위반이 있다는 조건에서 종류 분류 |
| 정답 사건 주변 25프레임, 사건의 종류 | **10/13 = 76.9%** | 사건 위치를 알고 입력한 진단; 자동 사건 검출률 아님 |
| 정상 영상에 위반 종류 출력 | **3/3** | 정상 클래스가 없어 모두 진로변경으로 분류 |
| 정상 영상의 5초 창, confidence ≥0.8 | **24/24** | 임계값 0.8만으로도 정상 배제에 실패 |
| 5초 창에서 정답 종류 + 사건 구간 중첩, confidence ≥0.8 | **10/13** | 대상·발생 시각 검증 없이 창이 겹치는 진단 지표 |
| CPU 지연 | 평균 **38.1ms**, p95 **41.7ms** / 시퀀스 | 입력 프레임 준비 제외 |

전체 영상 기준 신호 2/2, 중앙선 2/2, 실선 진로변경 6/8이다. `YT_0001_C09`, `YT_0003_C44`의 진로변경을 신호로 분류했다. 정답 사건 입력에서도 `YT_0001_C09`, `YT_0003_C10`, `YT_0003_C28`을 신호로 분류했다.

정상 영상 `141628`, `141956`, `150504`의 진로변경 확률은 각각 **0.998 / 0.987 / 0.872**였다. 높은 softmax 값을 위반 존재 확률로 해석하면 안 된다. 정상 클래스를 학습한 모델이나 독립적인 증거 확인 단계가 필요하다. 장면 배경을 활용하는지는 추가 실험 없이는 단정할 수 없다.

## 4. 공간 모델: 처리 속도와 증거 요소 관찰

| 모델 | 평균 ms/프레임 | p95 ms | warm adapter FPS |
|---|---:|---:|---:|
| YOLO 신호등·차량 | 11.4 | 15.4 | 87.4 |
| YOLO 중앙선용 차량 | 10.9 | 14.4 | 91.8 |
| YOLO 진로변경용 차량·터널등 | 10.9 | 16.4 | 91.5 |
| YOLO 안전모 | 9.8 | 13.3 | 102.4 |
| Mask R-CNN 정지선 | 90.7 | 109.7 | 11.0 |
| Mask R-CNN 중앙선 | 91.2 | 106.5 | 11.0 |
| Mask R-CNN 백색 차선 | 98.0 | 130.2 | 10.2 |
| Mask R-CNN 횡단보도·교차로 | 96.8 | 127.7 | 10.3 |

정답 사건 구간 안에 해당 종류의 primitive가 **어느 위치든 한 번 이상** 탐지된 사건 수:

| 증거 요소 | confidence ≥0.25 | ≥0.5 | ≥0.8 |
|---|---:|---:|---:|
| 실선 진로변경 구간의 white_solid | 9/9 | 9/9 | 9/9 |
| 중앙선 사건 구간의 황색 선 | 2/2 | 2/2 | 1/2 |
| 신호 사건 구간의 red_signal | 2/2 | 2/2 | 1/2 |
| 신호 사건 구간의 stop_line | 2/2 | 2/2 | 1/2 |
| 신호 사건 구간의 횡단보도 또는 교차로 | 2/2 | 2/2 | 2/2 |

이 표는 해당 차량이 넘은 선인지, 해당 차로를 제어하는 신호등인지 판단하지 않는다. 따라서 위반 recall로 읽으면 안 된다. 특히 white_solid 9/9는 점선 오분류 사례와 함께 봐야 한다.

## 5. 실제 오버레이에서 확인한 사례

1. **교량 실선 — `20260620_141927_EVT_1`, 7초:** 백색 차선 세 개가 0.98 / 0.95 / 0.81로 관찰된다. 선 위치를 보강하는 후보로 쓸 수 있다. 마스크 폭은 원본 학습 방식처럼 넓다.
2. **합법 점선 변경 — `20260620_141956_EVT_1`, 10초:** ego 오른쪽 점선 경계가 `white_solid` **0.99**로 표시된다. 선 주변을 연속된 마스크로 덮어 점선 간격을 보존하지 않는다. confidence만으로 실선 여부를 확정할 수 없다.
3. **중앙선 — `YT_0002_C00`, 12초:** 왼쪽 황색 이중선 1.00 외에 오른쪽 황색 연석도 yellow_solid 0.91로 탐지한다. 황색 선이 있다는 사실만으로 중앙선 역할이 성립하지 않는다.
4. **야간·저녁 — `YT_0003_C28`, 9초:** 중앙선 후보에 yellow_solid 0.52, yellow_double_solid 0.40이 겹쳐 나온다. 0.8 기준에서는 이 사건 구간의 황색 선 관찰이 빠진다.
5. **신호 — `YT_0001_C08`, 16초:** 적색 신호등과 여러 차량을 탐지한다. 각 차량과 관련 신호의 연결·정지선 통과 시점은 출력에 없다.
6. **정지선 — `YT_0001_C33`, 51초:** 넓고 일부 겹치는 정지선 후보가 0.74 / 0.37 / 0.33으로 보인다. 단일 마스크로 차량 통과를 판정할 수 없다.
7. **터널 — `YT_0003_C05`, 11초:** 차량·터널등·차선 주변 마스크를 관찰한다. 낮은 confidence 마스크에 천장 등 주변의 오류도 보인다. 위반 주체와 선 횡단은 별도 추적이 필요하다.
8. **안전모 — `YT_0001_C33`, 51초:** 이륜차에 no_helmet_motorcycle 0.93 출력이 있다. 이 영상 모음의 안전모 정답이 없어 정오 판정·recall은 보류한다. 검출 0건인 터널 프레임을 안전모 성능으로 해석하지 않는다.

로컬 비교 이미지:

![실선·점선·중앙선·신호등 오버레이](C:/Users/User/orca/ktc4-chonnam-2/.omc/aihub-models/run/evidence/comparison.jpg)

주석 영상은 `.omc/aihub-models/run/evidence/{bridge-solid,legal-dashed,signal-red}.mp4`에 저장했다. **예측은 1fps**, 표시 confidence는 **0.8 이상**이며 H.264 30fps 컨테이너로 프레임을 반복해 저장했다. 새로운 30fps 추론 결과가 아니다. 음성은 포함하지 않았다. 원본 미디어는 수정하지 않았다.

## 6. 추천 활용 구조

**우선 실험할 조합: 차량 YOLO 하나 + 필요한 선 종류의 Mask R-CNN 하나 + 기존 시간축 증거 확인.** 차량만 필요하면 car 단일 모델이나 car+tunnel_light 모델 하나를 선택하면 된다. 세 차량 모델을 모두 돌릴 이유는 현재 평가에서 확인하지 못했다.

- **Coarse 후보 보강:** 1~2fps로 차량·차선·신호등 위치를 얻고, 후보 구간과 관심 차량 crop을 만드는 입력으로 활용한다. 이것은 후보 선택 제안이며 이번 실험에서 후보 알고리즘의 성능을 측정한 것은 아니다.
- **실선·중앙선:** 후보 주변에서 프레임 밀도를 높이고 차량의 지면 접점과 선 중심선의 상대 위치 변화를 추적한다. 카메라 이동·곡선 도로·가림을 고려하고, white_solid 마스크 주변 원본 crop에서 실제 선의 연속성과 황색 선의 도로 역할을 추가 확인한다. 마스크 중심선 추출만으로 점선 오분류가 해결되지는 않는다.
- **신호위반:** 관련 신호등을 차량 진행 방향에 연결하고, 적색 점등 시점과 해당 차량의 정지선 통과 순서를 확인한다. 신호등 색 하나만으로 위반 판정을 만들면 안 된다.
- **LRCN:** 현재는 위반 확정·정상 필터에 쓰지 않는다. 장면 종류에 대한 보조 점수로 사용할지 비교하고, 이를 검출기로 쓰려면 정상 영상과 합법 점선 변경을 포함한 재학습·재평가가 필요하다.
- **안전모:** 별도 이륜차·머리 정답 영상을 준비해 crop 해상도와 rider–motorcycle 연결부터 평가한다. 이번 15개에 대한 사건 정확도는 주장하지 않는다.

실제 적용 여부는 위반 존재·대상 특정·시간 순서를 한 번에 검증하는 별도 end-to-end 평가로 결정해야 한다. 이번 결과로 확정한 것은 모델 실행 가능성, 제한된 종류 분류 성능, primitive 관찰과 실패 사례다.

## 7. 재실행과 검증 기록

프로젝트 의존성을 바꾸지 않고 `.omc/aihub-models/venv`에 별도 환경을 만들었다. Docker tar 85.6GB는 풀지 않았다. Detectron2의 Windows 설치 범위는 [공식 설치 문서](https://detectron2.readthedocs.io/en/latest/tutorials/install.html)에서 확인했다.

원본 R50 모델이 사용하지 않는 회전·deformable 연산의 import에 한해 빈 `detectron2._C` namespace를 제공했다. 해당 연산을 호출하면 오류가 발생하며 가짜 예측이나 대체 연산을 제공하지 않는다. 사용된 표준 ROIAlign / NMS는 v0.6 원본 코드의 torchvision native 연산이다([ROIAlign 소스](https://github.com/facebookresearch/detectron2/blob/d1e04565d3bec8719335b88be9e9b961bf3ec464/detectron2/layers/roi_align.py)). 네 모델 모두 모든 가중치가 strict 로드되고 실제 CUDA forward가 실행됐음을 확인했다. 원본 저장된 예측과 최종 코드의 프레임 재실행도 대조했다.

Git Bash, 저장소 루트에서 최초 준비:

```bash
uv venv --python 3.10 .omc/aihub-models/venv
uv pip install --python .omc/aihub-models/venv/Scripts/python.exe torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
uv pip install --python .omc/aihub-models/venv/Scripts/python.exe 'numpy<2' opencv-python==4.10.0.84 tensorflow==2.15.1 h5py pillow==9.5.0 'pydantic>=2,<3' typer fvcore iopath pycocotools omegaconf hydra-core termcolor cloudpickle tabulate tensorboard pandas seaborn requests tqdm psutil scipy gitpython ipython 'setuptools<81'
git clone --depth 1 --branch v7.0 https://github.com/ultralytics/yolov5.git .omc/aihub-models/yolov5
git clone --depth 1 --branch v0.6 https://github.com/facebookresearch/detectron2.git .omc/aihub-models/detectron2
```

소스 revision: YOLO `915bbf294bb74c859f0b41f1c23bc395014ea679`, Detectron2 `d1e04565d3bec8719335b88be9e9b961bf3ec464`. 설치된 정확한 패키지 목록은 로컬 `.omc/aihub-models/runtime-freeze.txt`에 보존했다. 원본 YOLO 코드의 pandas import를 충족하는 용도로 pandas가 필요하며, 평가 계산은 numpy로 수행했다.

준비된 로컬 환경에서:

```bash
PYTHONIOENCODING=utf-8 uv run --no-project --python .omc/aihub-models/venv/Scripts/python.exe python -m scripts.aihub_model_video_data src/daesingo/search/video .omc/aihub-models/run
PYTHONIOENCODING=utf-8 uv run --no-project --python .omc/aihub-models/venv/Scripts/python.exe python -m scripts.aihub_model_video_infer 'C:/Users/User/Downloads/교통법규 위반 상황 데이터/AI모델/2.학습모델파일' .omc/aihub-models/run .omc/aihub-models
PYTHONIOENCODING=utf-8 TF_CPP_MIN_LOG_LEVEL=2 uv run --no-project --python .omc/aihub-models/venv/Scripts/python.exe python -m scripts.aihub_model_video_lrcn 'C:/Users/User/Downloads/교통법규 위반 상황 데이터/AI모델/2.학습모델파일' .omc/aihub-models/run
PYTHONIOENCODING=utf-8 uv run --no-project --python .omc/aihub-models/venv/Scripts/python.exe python -m scripts.aihub_model_video_score .omc/aihub-models/run docs/modules/search/experiments/aihub-model-video-2026-10-04-results.json
```

전체 공간 모델 실행이 오래 걸리면 `--model-filter mask_lane,yolo_lane`처럼 나눠 실행할 수 있다. 실제 실행 중 MCP 호출은 300초 응답 제한에 걸렸지만 로컬 프로세스는 완료했다. 이후 8×15개 JSONL에서 프레임 수·시각을 전수 확인해 누락 없는 결과만 집계했다. 호출 timeout을 모델 추론 실패로 집계하지 않았다.

검증: 정답 파싱·다중 사건·소수점 구간·Python 3.10 해시 테스트 4개 통과, Python 3.10 기준 Ruff 검사, 외부 모델 소스 경로를 포함한 basedpyright 오류 0개, LSP 오류 없음. 모델 로딩·실영상 forward·기록된 결과 대조·오버레이 육안 검증·주석 영상 H.264 형식 확인을 수행했다. 원본 가중치·영상·기존 수정 파일 두 개는 보존했다.

데이터 설명 원문: [AI Hub 71555](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71555). 이 보고서의 성능 수치는 해당 페이지의 공개 벤치마크가 아닌 위 로컬 영상 실측이다.
