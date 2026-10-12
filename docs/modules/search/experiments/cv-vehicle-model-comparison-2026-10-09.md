# CV_LANE_TRACK v1 — 차량 7모델 추론·속도 측정 결과

작성일: 2026-10-09. 상태: **추론 완료 / 정확도 비교·선정은 차량 GT 미확보로 대기**.

차량 detector 7종이 동일한 원본 해상도 1,200프레임에서 각각 3회 CUDA FP32 추론을 완료했다. 저장된 예측은 총 25,200행이다. 현재 비교할 수 있는 것은 처리 속도다. 차량 bbox·동일 객체 ID를 사람이 검수한 정답이 없어 precision/recall, 사건 대상 검출률, 운영 confidence, 상위 2종 및 최종 detector는 아직 산출하지 않았다.

## 실행 범위와 입력

- 개발 영상 15개, 총 645.658초. calibration 5클립과 set1 비교 10클립의 구분을 manifest에 보존했다.
- 기존 원본 해상도 1fps 캐시 651장과 새 원본 해상도 5fps 패널 549장, 합계 1,200장.
- 5fps 패널은 차선 사건 11건의 앞뒤 3초와 정상 3클립의 7–13초다. 영상 경계 clamp, 겹치는 구간 병합, source frame index와 실제 fps에 따른 시각을 기록했다. C05 두 사건과 C47 경계 사건을 포함했다.
- 영상 SHA256, 원본 크기·fps·프레임 수, 기존 캐시의 시각·해시를 확인했다. 64px LRCN 캐시는 사용하지 않았다.
- 이번 실행은 차량 검출이다. 차선 검출·교차 후보 생성·Fine 호출은 실행하지 않았다.

## 측정 결과

단위는 ms/프레임이다. 각 반복의 p50·p95를 계산한 뒤 **3회 값의 중앙값**을 아래에 표시했다. 1fps와 5fps를 합친 동일 입력 패널 전체에 대한 수치다.

| ID | 모델 | adapter p50 | adapter p95 | 패널 1회 wall-clock 중앙값(초) | 실행 |
| --- | --- | ---: | ---: | ---: | --- |
| V1 | AI Hub YOLOv5 신호위반 — 차량 클래스 | 10.54 | 15.06 | 19.936 | 1,200 × 3 완료 |
| V2 | AI Hub YOLOv5 중앙선침범 — 차량 클래스 | 11.93 | 15.98 | 20.941 | 1,200 × 3 완료 |
| V3 | AI Hub YOLOv5 진로변경 — 차량 클래스 | 12.41 | 16.20 | 21.849 | 1,200 × 3 완료 |
| V4 | YOLO11n | 13.62 | 19.53 | 24.728 | 1,200 × 3 완료 |
| V5 | YOLO11s | 13.21 | 19.23 | 23.657 | 1,200 × 3 완료 |
| V6 | YOLO26s | 14.57 | 21.63 | 25.336 | 1,200 × 3 완료 |
| V7 | RT-DETR-L | 36.00 | 44.21 | 51.654 | 1,200 × 3 완료 |

이 패널에서 V1의 adapter 시간이 가장 짧았다. 이것으로 차량 검출 정확도나 사건 차량의 지속 검출 성능이 가장 좋다고 판단할 수는 없다. YOLO11n/s 사이 작은 시간 차이 역시 이 기기·패널에서의 관측값이다.

## 재현 조건과 시간 해석

- RTX 3060 12GB, driver 560.94, batch 1, 모델별 순차 실행, CUDA FP32. 실제 tensor dtype은 모두 `torch.float32`였다.
- AI Hub는 기존 Python 3.10.20·torch 2.5.1+cu121·YOLOv5 v7.0 loader 환경을 사용했다. 공개 모델은 별도의 Python 3.12.2·torch 2.5.1+cu121·Ultralytics 8.4.133 환경을 사용했다.
- 입력 크기 640. YOLO는 비율 유지 전처리, RT-DETR은 공식 640×640 전처리다. 실제 tensor shape는 반복별 `latency.json`에 저장했다. 1920×1080 입력에서 YOLO는 1×3×384×640, RT-DETR은 1×3×640×640이었다.
- confidence 0.01, max_det 300, NMS 모델 IoU 0.45. AI Hub car와 공개 모델 car/bus/truck을 `VEHICLE`로 합친 뒤 공통 IoU 0.7 NMS를 적용했다. YOLO26s는 고정 패키지의 실제 end2end decoder, RT-DETR은 공식 query decoder를 사용했다.
- warm-up은 평가 영상 대신 합성 1920×1080 빈 이미지로 20회 수행했다. 실제 평가 프레임으로 warm-up한 결과와 동일하다고 가정하지 않는다.
- adapter 시간에는 전처리·GPU 추론·후처리·CPU 결과 변환·공통 NMS가 포함된다. 시작과 끝에서 CUDA synchronize를 적용했다. JPEG 읽기·예측 파일 저장은 adapter 시간에서 제외하고 패널 wall-clock에 포함했다.
- 위 wall-clock은 각 패널 반복 루프 시간이다. 환경 설치·모델 로딩·warm-up·패널 추출·추적·차선 처리는 포함하지 않는다.
- GPU 메모리 원시 기록은 PyTorch peak allocated/reserved bytes다. `execution_summary.json`의 `peak_vram_mib`는 allocated tensor의 최대치이며 GPU 전체 점유량이 아니다.
- 3회 반복은 속도 측정용이다. 정확도 평가에서 같은 프레임을 3개 독립 표본으로 세지 않는다. 모두 이미 본 개발 영상이며 held-out 성능 근거가 아니다.

## GT와 남은 평가

로컬 사건 정답지는 사건 종류·시간 구간만 제공한다. 해당 15영상에 대응하는 사람이 검수한 차량 bbox·track ID GT는 찾지 못했다. 생성한 `vehicles_1fps.template.jsonl`, `vehicles_5fps.template.jsonl`은 빈 **라벨 작업용 양식**이다. 모든 행은 `reviewed=false`, `fully_labeled=false`이며, 11사건의 target은 모두 `TARGET_UNRESOLVED`다. 빈 양식을 차량이 없는 정답으로 채점하지 않았다.

원문 §2는 GT를 **모델 결과를 보기 전에** 작성하도록 요구한다. 추론은 GT 없이 실행하고 예측 캐시를 저장했으며, 예측 bbox 내용·overlay를 열어 GT를 유도하지 않았다. GT는 추론 입력 manifest에 포함되지 않는다.

| 단계 | 현재 상태 |
| --- | --- |
| 15영상·평가 패널 검증 | 완료 |
| 7종 환경·가중치·CUDA FP32 확인 | 완료 |
| 7종 실제 추론·3회 속도 측정 | 완료 |
| 1fps 모든 차량 bbox·ignore 영역 GT | 사람 작성·검수 필요 |
| 5fps 사건/이웃 차량 bbox·ID·가시성 GT | 사람 작성·검수 필요 |
| calibration confidence 고정 | GT 미확보로 미실행 |
| set1 정확도·작은 차량·사건별 지속 검출 채점 | GT 미확보로 미실행 |
| 상위 2종 동일 ByteTrack 재검증·최종 선정 | 상위 2종 미선정으로 미실행 |
| 예측 overlay 영상 검수 | GT 고정 전이므로 미실행 |

평가 준비 코드에는 GT의 검수·완전 라벨·프레임 coverage 검증, 1:1 IoU 매칭, 중복 FP, ignore-only 처리, AP50:95, 작은 차량 recall, bbox 하단 오차, precision≥0.90 운영점 선택 함수가 있다. **calibration→사건 채점→선정 전체 CLI와 ByteTrack 실험 runner는 아직 구현하지 않았다.** 이 보고서는 해당 단계의 완료를 주장하지 않는다.

GT가 고정되면 기존 저점수 예측 캐시로 confidence 후보를 채점하고 사건 주 지표로 상위 2종을 선정할 수 있다. 임의로 속도 상위 2종을 정확도 상위 모델로 대체하지 않는다.

## 검증과 산출물

- 모델 환경에서 관련 pytest **21 passed**. 프로젝트 기본 환경의 데이터·metric 테스트 **16 passed**. GT 미검수·부분 라벨·coverage 불일치·중복 프레임 거부, 기존 산출물 덮어쓰기 거부, 예측에 원본 시각·패널 정보 보존, TP/FP/AP 경계를 확인했다.
- 새 Python 스크립트 5개의 error LSP diagnostics는 없었다. 실제 비정방형 bbox 복원과 이웃 차량 연결은 GT 고정 후 overlay 검수까지 완료해야 한다. 공식 adapter 사용과 synthetic smoke만으로 이 검수를 대체하지 않는다.
- 새 스크립트 5개 `compileall`과 데이터 준비·추론·GT 검증 CLI의 실제 `--help` 실행은 모두 exit 0이었다. 실제 1fps/5fps 미검수 양식을 GT validator에 전달해 거부되는 것도 확인했다. 실제 추론의 input/adapter/runner 해시가 현재 파일과 일치함을 검증했다.
- 장시간 실행 도구는 300초에서 호출 timeout을 반환했지만 추론 프로세스는 계속 진행해 V1–V7 모두 완료했다. 모델별 마지막 완료 로그, 3개 예측 파일 각각 1,200행, 3회 latency 기록으로 완주를 확인했다. CUDA/OOM 모델 실패는 없었다.

로컬 산출물 루트는 `.omc/aihub-models/cv-lane-track-v1-2026-10-09/vehicle-comparison/`다. 영상·가중치·예측은 이 로컬 경로에 두고 Git에 추가하지 않는다.

| 경로 | 내용 |
| --- | --- |
| `input_manifest.json` | 1,200프레임 identity·시각·크기·해시, GT 없음 |
| `frames_5fps/` | 원본 해상도 549프레임 |
| `gt/*.template.*` | 미검수 라벨 작업 양식 |
| `smoke/V1..V7/smoke.json` | 별도 CUDA smoke 결과 |
| `inference/V1..V7/smoke.json` | 실제 실행 환경·가중치/source/input/adapter/runner 해시 |
| `inference/V1..V7/predictions.pass1..3.jsonl` | 모델별 3 × 1,200행 예측 |
| `inference/V1..V7/latency.json` | 반복별 p50/p95·메모리·실제 tensor shape·wall-clock |
| `execution_summary.json` | 7행 속도 요약과 예측 행 수 |
| `environment-*.freeze.txt` | AI Hub·공개 모델 환경의 패키지 목록 |
| `V1..V7-inference.log` | 진행·완료 로그 |

원래 전체 계획은 CV_LANE_TRACK v1 계획(`cv-lane-track-v1-2026-10-09.md`, 아직 미게시), 차량 비교의 세부 실행 계획은 실행 계획(`2026-10-09-cv-vehicle-model-comparison.md`, 로컬 메모·미게시)이다.
