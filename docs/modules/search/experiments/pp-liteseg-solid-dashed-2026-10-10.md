# PP-LiteSeg 실선·점선 구분 진단

2026-10-10 · 실제 모델 추론 완료 · 개발 영상 2개 · 정확도 미채점

**점선 클래스를 출력하는 공개 모델의 실행을 확인했다. 기존 AI Hub가 점선을 white_solid로 표시한 대표 장면에서 PP-LiteSeg는 dashed를 출력한다. 다만 동일 경계에 solid/dashed가 섞이는 출력과 비차선 구조물 오탐도 있어 모델 교체나 위반 판정의 근거로 바로 확정하지 않는다.**

## 입력과 모델

- 실선 변경 영상: `20260620_141927_EVT_1.avi`의 앞 20초.
- 합법 점선 변경 영상: `20260620_141956_EVT_1.avi`의 앞 20초.
- 영상별 2fps, 40장, 합계 **80장**. 원본 fps의 가장 가까운 source frame index를 사용했다. 실제 마지막 관측 시각은 약 19.492초다.
- 공식 [PP-Vehicle 차선 모델 문서](https://github.com/PaddlePaddle/PaddleDetection/blob/release/2.9/deploy/pipeline/docs/tutorials/ppvehicle_press_en.md)의 [pp_lite_stdc2_bdd100k.zip](https://bj.bcebos.com/v1/paddledet/models/pipeline/pp_lite_stdc2_bdd100k.zip)을 내려받아 실행했다. 이번 실행에서 가중치를 학습하거나 변환하지 않았다.
- 출력은 background=0, double_yellow=1, solid=2, dashed=3의 4개 클래스다.
- 전처리는 [공식 lane_seg_infer.py](https://github.com/PaddlePaddle/PaddleDetection/blob/release/2.9/deploy/pipeline/ppvehicle/lane_seg_infer.py)의 RGB, `/255`, mean/std 각각 0.5, NCHW float32를 따른다. **원본 1920×1080**을 그대로 추론했다.
- 원시 softmax의 argmax를 저장했다. 공식 위반 감지 예제의 `pred[pred == 3] = 0` 점선 제거, 이진화, Hough 선 추출은 적용하지 않았다. 임의의 선 종류 규칙이나 GT로 예측을 수정하지 않았다.
- 별도 Python 3.10.20 / PaddlePaddle 2.6.2 / NumPy 1.26.4 환경에서 **CPU FP32, 4 threads**로 실행했다. 프로젝트 환경은 변경하지 않았다.

## 직접 확인한 결과

검수 시점을 영상별 7/10/13초로 고정해 원본, 같은 시각의 AI Hub 2fps 출력, PP-LiteSeg를 나란히 비교했다. AI Hub 비교본은 이전과 같은 차량 모델과 백색 차선 모델, 표시 confidence 0.8을 사용한다. PP-LiteSeg는 클래스 argmax이므로 두 화면의 표시 개수나 confidence를 정량 정확도로 비교하지 않는다.

| 장면 | 관찰 |
| --- | --- |
| 점선 영상 10초 | AI Hub의 white_solid 연속 마스크와 달리 PP-LiteSeg가 ego 오른쪽 점선 경계를 dashed로 표시한다. |
| 점선 영상 7/13초 | dashed 출력이 나타나지만 7초의 같은 경계 가까운 부분에는 solid도 섞인다. 한 번의 dashed 출력만으로 안정적인 경계 속성이 확립된 것은 아니다. |
| 실선 영상 7초 | 주 차선 페인트를 solid로 표시하지만 교량 상부 철골과 도로 외곽에도 일부 solid 오탐이 있다. |
| 실선 영상 10/13초 | 오른쪽 경계에 solid/dashed 출력이 섞인다. 프레임 내·프레임 간 종류 안정성을 추가 확인해야 한다. |
| 공통 | 연석/방호벽·보닛 주변의 일부 비차선 영역이 차선으로 분류된다. 마스크가 끊긴 페인트 사이를 메우는 출력도 보인다. |

영상 색상은 **초록=solid, 분홍=dashed, 노랑=double_yellow**다. 점선 클래스가 있다고 해서 점선 페인트의 모든 틈이 원시 마스크에 보존되는 것은 아니다.

픽셀 GT·경계별 종류 GT가 없으므로 accuracy, mIoU, precision/recall, 모델 우승은 계산하지 않았다. 두 영상은 이미 본 개발 자료이며 독립 검증 데이터가 아니다. 황색 이중선의 분류 성능도 이번 두 클립으로 평가하지 않았다.

처리시간 p50은 실선 영상 2250.02ms/장, 점선 영상 2249.69ms/장이다. 전처리·CPU 추론·출력 복사·argmax·유한값 검사를 포함하고 시각화/저장은 제외한다. 별도 warm-up을 하지 않은 단일 실행 진단이며 GPU 속도 또는 기존 CUDA 모델과의 속도 비교가 아니다. **2fps는 관측 간격이고 실시간 처리속도는 아니다.**

## 산출물과 검증

로컬 루트: `C:/Users/User/orca/ktc4-chonnam-2/.omc/pp-liteseg-lane-2026-10-10/`.

- `bridge-solid-pp-liteseg-2fps.mp4`, `legal-dashed-pp-liteseg-2fps.mp4`: 각 20초, 1280×720, H.264, 원본 음성 AAC. 2fps 관측을 30fps 컨테이너에서 반복해 표시한다.
- `bridge-solid-comparison.jpg`, `legal-dashed-comparison.jpg`: 원본/AI Hub/PP-LiteSeg, 영상별 7/10/13초 3행 비교.
- 영상별 폴더의 `masks/*.npy`: 원본 크기 uint8 클래스 마스크 40장. `frames/*.jpg`: 표시 이미지 40장. `predictions.jsonl`: source index/time, 클래스별 픽셀 수와 선택 클래스 평균 확률, 처리시간.
- `manifest.json`: 공식 모델 URL, 가중치·입력·실행 코드·참고 소스 SHA256, 환경, 전후처리, sampling fps.
- `artifact_audit.json`: 전체 80행·80마스크·80표시 이미지와 0.5초 sampling, 클래스 범위, 원시 마스크 픽셀 수 대조 **PASS**.
- `environment.freeze.txt`, `inference.log`, `run.py`, `lane_seg_infer.official.py`: 재현 환경과 실제 실행 기록.

두 MP4 전체 디코딩에서 오류가 없음을 확인했다. 실행 코드 compileall 통과, error LSP diagnostics 없음, programming no-excuse 검사 통과. 원본 영상·가중치와 다른 작업 파일은 보존했다. 앱 운영 경로에는 연결하지 않았다.

결론: **실선·점선 구분 후보로 후속 평가할 수 있다.** 동일 경계의 속성 검수와 시간축 안정성, 가림·야간·터널·황색선 사례를 확보한 뒤 사용 여부를 결정해야 한다.
