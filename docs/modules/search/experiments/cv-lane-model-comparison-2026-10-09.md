# CV_LANE_TRACK v1 — 차선 모델 출력·속도 비교

작성일: 2026-10-09. 상태: **L1·L3 추론 및 육안 진단 완료 / L2 실행 환경 차단 / 정량 정확도 미평가**.

사용자가 차량 GT 검수를 보류하고 차선 비교부터 진행하도록 선택했다. 이에 이번 실험은 사람이 작성한 차선 정답 없이 실행할 수 있는 추론·속도·출력 진단으로 한정했다. L1 AI Hub 백색·황색 차선 모델 조합과 L3 UFLDv2가 같은 1,200프레임을 각각 3회 처리했다. 총 예측 7,200행과 모델별 42개 overlay, 원본/L1/L3 비교 시트 14개를 보존하고 직접 확인했다. CLRerNet은 실제 추론을 실행하지 못했다. 정확도 우승 모델이나 최종 조합은 선정하지 않았다.

## 입력과 측정 결과

이전 차량 실험에서 검증한 개발 영상 15개, 원본 해상도 1fps 651장과 사건·정상 5fps 패널 549장을 그대로 사용했다. calibration/set1 구분을 manifest에 보존했다. 추론·검수 영상은 이미 본 개발 자료이므로 held-out 성능 근거가 아니다.

아래 시간은 각 반복의 p50·p95를 계산한 뒤 **3회 값의 중앙값**이다. 같은 GPU에서 후보를 순차 실행했다. L1 시간에는 백색·황색 모델 두 개와 마스크 중심선 추출을 모두 포함한다.

| ID | 후보 | adapter p50(ms/프레임) | adapter p95(ms/프레임) | 1,200프레임 wall 중앙값(초) | 결과 |
| --- | --- | ---: | ---: | ---: | --- |
| L1 | AI Hub Mask R-CNN R50-FPN 백색＋황색 | 195.45 | 305.14 | 264.457 | 1,200 × 3 완료 |
| L2 | CLRerNet⋆ DLA34 EMA | 미측정 | 미측정 | 미측정 | CUDA 확장 환경 차단 |
| L3 | UFLDv2 ResNet34 CULane | 51.42 | 90.30 | 76.725 | 1,200 × 3 완료 |

이 기기·패널에서 L3 adapter p50은 L1 조합보다 약 3.80배 짧았다. 두 후보의 전처리·출력 표현·후처리가 다르므로 이 차이는 실제 adapter 조합 비용 비교다. 이것으로 차선 정확도 우위를 주장하지 않는다. L2 미실행으로 세 후보 전체 비교도 완료되지 않았다.

| 후보 | 반복별 p50(ms) | 반복별 p95(ms) | 반복별 wall(초) |
| --- | --- | --- | --- |
| L1 | 195.44560 / 195.44885 / 197.08825 | 304.39478 / 305.13836 / 307.50479 | 264.45690 / 264.22670 / 268.45877 |
| L3 | 51.41635 / 51.49695 / 51.01005 | 89.82997 / 92.07710 / 90.29612 | 76.72518 / 77.74441 / 76.27588 |

## 공식 모델과 로컬 변환

- L1은 기존 AI Hub `model_차선탐지_진로변경.pth`와 `model_차선탐지_중앙선침범.pth`를 사용한다. 기존 Detectron2 BGR short-edge 800/max-edge 1333 전처리, instance confidence 0.25를 유지했다. 정지선·교통영역 모델은 제외했다.
- L1 원시 instance 마스크와 모델이 제공한 white_solid/yellow_solid/yellow_double_solid·confidence를 저장했다. 연결 성분마다 면적 25px 이상·높이 10px 이상을 남기고 원본 좌표에서 5행 간격의 x 중앙값으로 polyline을 추출했다. 서로 끊어진 성분은 연결하지 않는다. skeleton이나 곡선 fitting은 사용하지 않았다. 따라서 아래 L1 관찰은 **모델＋이 고정 중심선 추출**에 대한 결과다. 마스크 분기·가로 구조의 행 중앙값도 추출된 선을 왜곡할 수 있다.
- L3는 [공식 CULane Res34 설정](https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2/blob/c903880678454dfd9b55a63022368db05c00bc6d/configs/culane_res34.py)과 공식 배포 `culane_res34.pth`를 사용했다. PIL RGB 533×1600 resize·ImageNet 정규화 후 하단 320행, 실제 CUDA 입력 1×3×320×1600이다. 72개 row anchor, 81개 column anchor와 [원본 demo의 pred2coords](https://github.com/cfzd/Ultra-Fast-Lane-Detection-v2/blob/c903880678454dfd9b55a63022368db05c00bc6d/demo.py)를 그대로 적용했다.
- 공식 UFLDv2에는 추론에 불필요한 DALI/학습용 import가 섞여 있다. 로컬 wrapper는 고정 원본 source에서 초기화 함수와 decoder 함수만 AST로 그대로 읽어 실행한다. 원본 forward·decoder는 수정하지 않았으며 checkpoint 전체를 strict load했다. decoder의 이미지 경계 좌표 관례(y가 이미지 높이와 같은 끝점 포함)를 유지했다.
- L3 공식 demo는 선 전체 confidence나 색·실선/점선·중앙선 역할을 제공하지 않는다. confidence는 null, semantic_label은 UNKNOWN으로 저장했다. 그림의 색은 선 구분용이며 법적 종류를 뜻하지 않는다. 표시 숫자도 프레임 내부 인덱스이므로 시간에 걸친 동일 차선 ID가 아니다.
- L2는 [공식 설치 지침](https://github.com/hirotomusiker/CLRerNet/blob/dae038f67da57e292e5293a68c9c1c2922de13c2/docs/INSTALL.md)과 [v0.1.0 EMA checkpoint](https://github.com/hirotomusiker/CLRerNet/releases/tag/v0.1.0)를 확보했다. host에 native nvcc가 없고 기존 Docker backend도 기동하지 못해 CUDA lane NMS 환경을 만들지 못했다. `docker desktop start --detach` 요청 후 Inference manager의 dockerInference socket 시작이 “The file cannot be accessed by the system / filename, directory name, or volume label syntax is incorrect”로 실패했다. `docker info`로 작동하는 Linux engine을 확인하지 못했다. CPU 대체 추론은 없으며 오류를 `L2/failure.json`에 저장했다.

## 육안 진단

모델을 실행하기 전에 사건 시간만으로 11사건의 앞·중간·뒤와 정상 3클립의 7·10·13초에 가까운 프레임을 고정했다. 경계 clamp와 실제 프레임 시각은 `review_panel.json`에 있다. 예측이 잘 나온 장면으로 검수 대상을 교체하지 않았다. 총 42개 시점의 원본/L1/L3를 나란히 놓은 14개 시트를 모두 직접 확인했다.

| 시트 | 직접 확인한 출력 특징 |
| --- | --- |
| 141927 사건 | L1 초반에는 겹치거나 끊어진 선이 많다. L3는 여러 경계를 연속적으로 그리지만 하단 보닛과 가려진 부분까지 연장한다. |
| youtube_clip_01 사건 | 근접 차량이 도로를 가리는 장면에서 L3 선이 차체를 가로지르고 크게 꺾인다. L1 추출 선도 차량 주변에서 분기·단절된다. |
| C05 첫 사건 | 터널에서 L1 선이 여러 조각으로 중복된다. L3는 주 경계를 길게 그리지만 차량 가림을 통과해 이어지는 부분이 있다. |
| C05 둘째 사건 | L1 일부 추출 선이 터널 상부 방향으로 뻗는다. L3 출력은 비교적 연속적이나 가린 구간도 이어 그린다. |
| C00 사건 | 중앙 황색선과 오른쪽 황색 연석 주변에 선이 나온다. 색·형상만으로 중앙선 역할을 확정할 수 없다. |
| C09 사건 | L1은 조각·중복 출력이 많다. L3 뒤 시점의 교차로에서는 짧은 안쪽 선 두 개만 남는다. |
| C39 사건 | L1이 빗금 구역·이웃 차선 주변에 여러 선을 추출한다. L3 외곽 선 일부가 차량을 통과한다. |
| C47 경계 사건 | 두 후보 모두 근접 픽업 차체 위를 통과하는 선이 있다. 이를 실제 보이는 도로 선으로 사용할 수 없다. |
| C10 사건 | L1은 세 시점에 하늘 쪽으로 뻗는 추출 선이 있다. L3는 주 경계가 연속적이나 우측 바깥 경계는 굴곡이 크다. |
| C28 사건 | L1이 중복·분기된 선을 추출한다. 뒤 시점에서 L3 우측 선이 흰 차량 차체 위로 굴곡지게 이어진다. |
| C44 사건 | L1 선은 여러 조각으로 나뉜다. L3는 다리 그림자에서도 네 선을 유지하지만 가림 구간의 실제 위치 정답은 없다. |
| 141628 정상 | L1 우측에 여러 짧은 경계가 겹친다. L3는 세 긴 선을 그리며 하단 보닛까지 연장한다. |
| 141956 정상 | 두 후보 모두 전방 도로의 여러 경계를 출력한다. L3는 하단 보닛까지 선을 이어 그린다. |
| 150504 정상 | 와이퍼가 시야를 가린 중간 시점에도 선이 출력된다. L3 일부 선이 와이퍼·보닛 위까지 이어지거나 굴곡진다. |

첫 반복에서 L1은 polyline이 없는 프레임 1/1,200, L3는 96/1,200이었다. L1 전체 추출 segment는 14,580개, L3는 3,924개다. **빈 출력은 FN/recall이 아니고 segment 개수는 정확도가 아니다.** L1은 두 모델과 마스크 연결 성분별 조각을 합치며, L3는 공식 decoder가 선택한 최대 네 경계를 출력한다. 출력 단위가 달라 개수로 우열을 정할 수 없다.

## 재현·검증

- 같은 기존 Python 3.10.20, torch 2.5.1+cu121, torchvision 0.20.1+cu121, numpy 1.26.4, OpenCV 4.10.0, Pillow 9.5.0 환경을 별도 프로세스에서 사용했다. RTX 3060 12GB, driver 560.94, batch 1, CUDA FP32, CPU threads 4, cudnn benchmark=true다.
- warm-up은 manifest 첫 실제 프레임을 20회 사용했다. 로딩과 warm-up을 측정 반복에서 제외했다. L1 실제 backbone 입력은 두 개의 1×3×768×1344, L3는 1×3×320×1600이었다. 원본 입력 영상들은 원본 크기를 유지하며 모델별 공식 전처리만 다르다.
- adapter 시간은 전처리·추론·decoder·CPU 결과 변환과 L1 공통 중심선 추출을 포함하며 앞뒤 CUDA synchronize를 적용했다. JPEG 읽기·JSONL 저장은 adapter에서 제외하고 각 반복 wall-clock에 포함했다. overlay와 시트 생성은 측정 반복 뒤에 수행했다. 환경 설치·모델 로딩·warm-up·패널 추출·시각화는 표의 wall에 포함하지 않는다.
- 최대 PyTorch allocated tensor는 L1 828.72MiB, L3 905.23MiB였다. reserved bytes도 별도 저장했다. GPU 전체 점유량으로 해석하지 않는다.
- UFLDv2 source SHA: `c903880678454dfd9b55a63022368db05c00bc6d`; CLRerNet: `dae038f67da57e292e5293a68c9c1c2922de13c2`; Detectron2: `d1e04565d3bec8719335b88be9e9b961bf3ec464`. 세 원본 checkout의 변경 없음도 확인했다.
- 입력 manifest SHA256: `bede1c7f97b8666eb007ec3bf269a263f5c88e1a9ed15a15b839417cfc711282`. 가중치·검수 목록·실행 코드 SHA256은 모델별 metadata/failure JSON에 있다. 현재 코드와 완료 실행의 해시가 일치한다.
- 최종 관련 테스트 **6 passed**. 원본 좌표 decoder, 연결 성분 사이 공백, 빈 출력·UNKNOWN, 기존 결과 덮어쓰기 거부 경계를 검증했다. 5개 Python 파일 compileall 통과, CLI help 정상, 3개 실행 코드의 error LSP diagnostics 없음. 별도 읽기 전용 코드 검토 CLEAR/APPROVE.
- 실제 완료 로그 확인 뒤 전 예측 7,200행을 schema로 읽어 manifest 순서·frame identity·model ID·유효 좌표와 시간을 검증했다. 저장된 p50/p95·빈 출력·segment 수를 원시 행에서 재계산했다. 모델별 review 42장과 비교 시트 14개, L1 최종 review가 육안 진단에 사용한 첫 반복 overlay와 byte 동일함을 확인했다. `artifact_audit.json` 결과 PASS.

실행 코드는 `scripts/cv_lane_track_lane_geometry.py`, `scripts/cv_lane_track_lane_adapters.py`, `scripts/cv_lane_track_lane_infer.py`다. 기존 차량 bbox 예측 캐시는 열람하지 않았다. 앱 운영 경로·추적·교차 후보·Fine 호출은 이번 단계에서 실행하지 않았다.

로컬 evidence root: `.omc/aihub-models/cv-lane-track-v1-2026-10-09/lane-comparison/`.

| 파일/폴더 | 내용 |
| --- | --- |
| `execution_summary.json`, `artifact_audit.json` | 2종 완료·1종 차단 요약과 전체 행/해시 검증 |
| `inference/L1`, `inference/L3` | metadata, latency, predictions.pass1/2/3.jsonl, review 42장씩 |
| `review_panel.json`, `review_frame_ids.json` | 사전 고정 검수 시점·실제 프레임 identity |
| `review-comparison` | 14개 원본/L1/L3 × 앞/중간/뒤 시트 |
| `L2/failure.json` | 실행하지 못한 환경·공식 source/weight·오류 |
| `L1-inference.log`, `L3-inference.log`, `smoke` | 실제 완료 로그와 CUDA FP32 smoke |
| `sources`, `weights` | 고정 공식 소스와 체크포인트 |
| `environment.freeze.txt`, `environment_provenance.json` | 추론 환경 전체 패키지 목록과 SHA256 |

## 라벨링과 다음 판단

**지금 수행한 출력·속도 비교에는 라벨링이 필요하지 않다.** 차선 polyline 위치 오차·누락·잘못된 연결을 숫자로 비교하거나 실선/점선·색·중앙선 역할의 정확도를 채점하려면 사람이 검수한 정답이 필요하다. 사건 시간 정답만으로 이 지표들을 계산할 수 없다. 이번에 예측을 본 뒤 만드는 라벨을 “예측을 보기 전에 고정한 독립 GT”로 설명해서도 안 된다.

L3는 속도와 비교적 연속적인 출력 때문에 다음 geometry 실험의 잠정 후보로 검토할 수 있다. 그러나 차체·보닛·와이퍼를 관통하는 선, 의미 분류 UNKNOWN, L2 미측정이 남아 있어 정확도 최종 선정 근거는 없다. 세 후보를 모두 비교하려면 L2 공식 CUDA 환경이 필요하다. 이후 정량 평가·교차 실험에는 독립 검수한 차선 위치·가시성·관련 경계/종류/역할과 사건 차량의 bbox·ID가 필요하며, 해당 작업은 이번 보고서의 완료 범위에 포함하지 않는다.
