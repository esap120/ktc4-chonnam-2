# CV_LANE_TRACK v1 — 전체 영상 추적 진단

작성일: 2026-10-09. 상태: **실행·artifact 감사·육안 진단 완료, GT 정확도 미평가**.

전체 15개 영상의 5fps 3,233프레임에서 임시 V1 차량 검출＋L3 UFLDv2 차선 geometry를 실행하고, 같은 V1 검출을 ByteTrack과 BoT-SORT에 넣었다. 두 추적기 모두 완료했다. 추적 adapter 시간 중앙값은 ByteTrack 1.96ms, BoT-SORT 8.14ms였다. 정확도 우열이나 최종 모델 조합은 선정하지 않았다.

사용자는 GT 라벨링을 미루고 차선 출력 비교 다음 작업을 요청했다. 이번 단위는 실행 계획(`2026-10-09-cv-tracking-diagnostic.md`, 로컬 메모·미게시)에 고정한 전체 영상 추적 진단이다. 원문의 GT 기반 detector 상위 2종 선정 대신 기존 V1 기준선 한 종을 임시 사용했다. L3 역시 실행 가능한 geometry 후보로 사용했으며 정확도 평가로 선정한 모델이 아니다. 교차 후보·위반 판정·C0–C5·Fine 호출·운영 적용은 이번에 실행하지 않았다.

## 입력과 고정 조건

- 입력: 기존 15영상 전 구간, 원본 해상도 JPG quality95, 실제 source index/fps 기준 시각, 5fps. 사건 구간만 추론하지 않았다.
- 4개 AVI 각 101프레임, youtube_clip_01 28프레임, YT_0002_C00 101프레임, 나머지 set1 9클립 각 300프레임으로 총 3,233프레임.
- 추론 source inventory에는 파일·해시·fps·전체 프레임 수만 담았다. 사건 시각·차량 ID·차선 정답은 모델/추적 입력에 전달하지 않았다.
- V1: AI Hub 차량 검출 원본 YOLOv5 adapter, confidence 0.01. L3: 공식 UFLDv2 CULane ResNet34 CUDA FP32. 각 20회 warmup 후 전체 한 번씩, 모델별 별도 프로세스.
- RTX3060 12GB, driver560.94. perception은 기존 Python3.10.20 / torch2.5.1+cu121 환경을 유지했다. tracking은 새 독립 Python3.12.2 환경에서 CPU로 실행했다.
- 두 추적기: Ultralytics8.4.133 / lap0.5.12. high/new 0.25, low0.01, match0.8, fuse_score=true, track_buffer=5. high/new는 GT로 고른 운영점이 아닌 임시 공통 설정이다.
- ByteTrack은 GMC 없음. BoT-SORT는 sparseOptFlow GMC, proximity0.5, appearance0.8, ReID=false. 별도 외형 모델은 실행하지 않았다. 설정 JSON에는 공통 설정 객체의 GMC 관련 값도 저장되지만 ByteTrack은 이를 사용하지 않는다.
- 두 방식 모두 클립 경계에서 tracker/GMC/ID 상태를 초기화했다. 이번 비교에는 scene-cut reset을 적용하지 않았다.
- 현재 검출에 연결된 관측만 출력했다. 원본 detection index·bbox와 Kalman 보정 bbox를 따로 저장하고, 화면은 원본 검출 bbox를 그렸다. lost/prediction-only box는 출력하지 않았다.

공식 추적기 기능 설명은 [Ultralytics tracking 문서](https://docs.ultralytics.com/modes/track/), 이번 동작 계약은 고정 버전의 [ByteTrack 소스](https://github.com/ultralytics/ultralytics/blob/v8.4.133/ultralytics/trackers/byte_tracker.py)와 [BoT-SORT 소스](https://github.com/ultralytics/ultralytics/blob/v8.4.133/ultralytics/trackers/bot_sort.py)를 기준으로 확인했다.

## 실행 결과

| perception | 처리 프레임 | adapter p50 / p95 | 전체 pass 벽시계 | peak CUDA allocated |
|---|---:|---:|---:|---:|
| V1 차량 | 3,233 | 13.82 / 16.81ms | 58.58초 | 51,066,880bytes |
| L3 차선 | 3,233 | 54.31 / 95.73ms | 209.83초 | 949,207,040bytes |

perception adapter 시간에는 CUDA 동기화를 적용했다. 벽시계에는 JPEG 읽기와 JSON 저장이 포함되고 모델 로딩·warmup·입력 캐시 생성은 제외된다. 입력 tensor는 V1 1×3×384×640, L3 1×3×320×1600이었다. 이번 값은 전체 캐시 생성 1회 측정이며 앞선 3회 모델 비교의 대체 benchmark가 아니다.

| tracker | adapter p50 / p95 | 저장 포함 벽시계 | 검출 연결 관측 수 | 클립별 raw ID 합 | 추적 출력 없는 프레임 |
|---|---:|---:|---:|---:|---:|
| ByteTrack | 1.96 / 3.34ms | 46.68초 | 16,558 | 595 | 158 |
| BoT-SORT | 8.14 / 25.68ms | 72.39초 | 16,693 | 682 | 195 |

tracker adapter 시간은 검출 결과의 변환·association·BoT-SORT GMC를 포함하고, perception·JPEG 읽기·overlay·영상 저장은 제외한다. 벽시계는 캐시 읽기·overlay·MP4 저장을 포함한다. cv2 threads=4. 각각 한 번 실행했으므로 반복 측정 분산은 알 수 없다.

0.25초를 넘겨 같은 ID가 재등장한 관측 간격은 ByteTrack 374건, BoT-SORT 217건이었다. 최대 간격은 둘 다 약 1.4초였다. 이것은 실제 동일 차량의 재식별 정확도나 ID switch 수가 아니다. raw ID가 적은 것은 연결 유지 또는 잘못된 병합일 수 있고, 많으면 실제 진입 또는 분절일 수 있다. 관측 수·출력 없는 프레임 수도 recall이 아니다. GT 없는 수치로 정확도 순위를 만들지 않는다.

## 직접 확인한 출력과 후속 영향

추적 실행 전에 검수 프레임을 고정했다. 각 클립 중간의 연속 6프레임(약 1초) 15시트와 기존 차선 검수의 사건/정상 전후 14시트를 새 전체 캐시에 대응시켰다. 중복을 제외한 128시점, 총 29시트의 원본｜ByteTrack｜BoT-SORT를 모두 직접 확인했다. 전후 3시점은 연속 영상이 아니므로 그 사이 ID 안정성이나 사건 적중을 판정하지 않았다. 전체 30개 MP4는 디코딩 검증했지만 전체 시간을 사람이 재생 검수한 것은 아니다.

| 사례 | 확인한 화면 | 후속 처리에 미치는 영향 |
|---|---|---|
| 141628·141927·141956 및 터널 C10 중간 연속 구간 | 전방 차량의 박스와 ID가 짧은 구간에서 두 방식 모두 유지되는 사례 | 추적 입력과 표시가 동작한다. 전체 ID 정확도 보증은 아니다 |
| youtube_clip_01 3초 부근 | 가까운 흰 차량 추적은 양쪽에 표시되지만 L3 선이 차체 위에서 심하게 꺾임. 왼쪽 차량의 ID 표시도 두 방식이 다름 | 가려진 차체 위 geometry만으로 교차를 확정할 수 없다 |
| YT_0002_C00 9.4–10.4초 | 블러된 전방 차량은 초반 양쪽 모두 관측 박스가 없다가 뒤에 나타남 | 검출 공백을 이동 증거로 보간하면 안 된다 |
| YT_0001_C08 29.4–30.4초 | 보행자 위치에 VEHICLE 박스가 이어지는 사례, L3 선은 6프레임 모두 없음 | 차량 범주·차선 유효성 확인 없이 후보를 만들면 오탐 위험 |
| YT_0001_C47 29.4–30.4초 | 흰 SUV 뒤쪽에 전체 박스와 작은 겹침 박스가 서로 다른 ID로 양쪽에 표시 | upstream V1 중복 검출이 두 추적기로 전달됨. 중복 후보 진단 필요 |
| YT_0001_C09 전후 및 C39 중간 구간 | 겹치는 검출/추적 박스, 차량 위로 이어지는 선 | 한 차량/동일 경계의 시간 연결을 따로 검증해야 함 |
| YT_0003_C28 29.4–30.4초 | 버스·전방 차량·이륜차에 대한 박스가 표시되고 가까운 버스 위로 선이 이어짐 | geometry는 도로에서 관측된 실선/점선의 의미 판정이 아님 |
| 150504 10초 부근 | 와이퍼 가림 중에도 앞차 박스는 남지만 선이 흔들림 | 가림/geometry 품질 gate 필요 |
| YT_0003_C44 29.4–30.4초 | 주 차량 표시 외 주변 차량 ID/활성 박스가 두 방식에서 달라짐 | GMC 유무의 정확도 효과는 GT로 따로 평가해야 함 |

나머지 전후 시트도 출력·원본 대응을 확인했다. 위 사례는 정성 진단이며 FP/FN/ID switch 정답 라벨을 만든 것이 아니다. 기존 vehicle-comparison bbox 캐시는 열지 않았다. 이번 새 차량 overlay는 추적 진단 범위에서 확인했으므로, 이 화면의 영향을 받아 나중에 만든 라벨은 사전 독립 GT라고 부르지 않는다.

`track_buffer=5`와 실제 `max_frames_lost=5`를 확인했지만 정확히 1초 뒤 연결이 끊긴다는 보장은 없다. 고정 upstream은 association 후 stale removal을 수행하며 Removed 상태의 lost-pool 정리가 다음 update에 이뤄지는 경우가 있다. 실제 같은-ID 간격 1.4초도 관측했다. 후속 교차 상태는 ID가 같더라도 관측 간격이 `2/fps+0.05=0.45초`를 넘으면 별도로 초기화해야 한다. scene cut, 차선 누락·급변·중복 박스에 대한 처리도 후보 구현 단계의 범위다.

L3 선 옆 0–3은 모델의 출력 slot 표시다. 시간적으로 동일한 차선 경계 ID가 아니다. 색이나 slot으로 실선·점선·중앙선 종류를 판정하지 않으며 모두 UNKNOWN으로 표시했다.

## 검증과 산출물

로컬 evidence root는 `C:/Users/User/orca/ktc4-chonnam-2/.omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/`다. 저장소에는 재현 코드·이 보고서만 두고 원본/예측 영상은 로컬에 유지한다.

- `source_inventory.json`, `input/input_manifest.json`: 15개 source hash·3,233개 JPG hash·source index·시각을 감사했다.
- `perception/V1`, `perception/L3`: 각각 3,233행. 원본 시각과 순서·Pydantic 스키마 확인.
- `ByteTrack`, `BoT-SORT`: 각각 `tracks.jsonl`, `summary.json`, 128장 `review/`, 15개 `videos/`.
- `review_frames.json`, `review_panels.json`, `review-comparison/`, `manual_qa.json`: 사전 고정 선택과 29개 비교 시트. 루트 에이전트가 전부 확인하고 검수 시트 해시를 보존했다.
- `artifact_audit.json`: PASS. perception6,466행＋tracking6,466행 프레임 대응·현재 코드 해시·모든 관측의 원본 detection index/bbox 일치. 프레임 내 중복 ID/index 없음. MP4 30개를 끝까지 디코딩하여 5fps·960×540·프레임 수 확인.
- `execution_summary.json`: 전체 raw 집계와 tracker JSONL 해시. `tracking-runtime-freeze.txt`, `tracking-runtime-provenance.json`: 실제 설치 버전 및 upstream 소스 해시.
- 테스트: 독립 tracking 환경 **7 passed (10.08초)**. 기본 `.venv`는 데이터 테스트 **2 passed**, torch 없는 선택적 tracker 모듈 **1 skipped**. 기본 환경의 skip을 추적 테스트 통과로 계산하지 않았다.
- 변경 Python 7파일 compileall 통과, LSP error 없음, programming no-excuse checker 7파일 위반 없음. 프레임 준비·perception·tracker state·시각화·runner를 책임별로 나눴으며 과대 모듈·Any/ignore·광범위 예외 없음.
- 읽기 전용 코드 검토에서 재현 테스트 환경 문서 누락을 지적했다. 아래 고정 환경 명령을 추가하고 선택적 테스트 수집과 실제 환경 7개 테스트를 모두 확인했다.

주요 SHA256:

| 대상 | SHA256 |
|---|---|
| full input manifest | `d2da138ab98106d5a96a4149b4ce03d2e4e9178580d8f3d6f188bafc5d3ac2be` |
| V1 weight | `507bd154524c0ebcae8f6c92f4eac2e7feb31e5e2c2bf2e3d10d64a717f0ab38` |
| L3 weight | `1b4ca8385122f74c46a2e274950cdb5eb132ff97aa1ab1311550526d83caebf6` |
| V1 predictions | `b096743f6cce7f676e0c63cb2e2c7e5f73fbff26cfec39efb75c2ed768f081b5` |
| L3 predictions | `a05d3b87885cbdc48010720dbb2bba8108afd971fe300ea43b87c17a3fac6613` |
| ByteTrack tracks | `3d1cc33394f0dc23f9a9dd6e5faa5ae84bb55bbb8789c565ad58fc9331ac15df` |
| BoT-SORT tracks | `20de232074aa3b8e244b58d6105670f1c4a0bf8c4da2570095698f1dbd771181` |

V1 source revision: `915bbf294bb74c859f0b41f1c23bc395014ea679`. UFLDv2 source revision: `c903880678454dfd9b55a63022368db05c00bc6d`. 상세 resource 경로·adapter 코드 해시는 각 perception summary에 보존했다.

## 재현 명령

프로젝트 루트에서 실행한다. 기존 evidence 폴더에는 재실행하지 않는다. 아래 새 OUTPUT 경로는 비어 있어야 하며 runner는 덮어쓰기를 거부한다. GPU perception의 기존 환경·source·weight 확보 절차는 [차량 기록](cv-vehicle-model-comparison-2026-10-09.md)과 [차선 기록](cv-lane-model-comparison-2026-10-09.md)을 따른다.

새 독립 tracking 환경 생성 예시(기존 tracking-venv는 보존):

```bash
uv venv --python 3.12 .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-venv-repro
uv pip install --python .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-venv-repro/Scripts/python.exe --extra-index-url https://download.pytorch.org/whl/cu121 'torch==2.5.1+cu121' 'torchvision==0.20.1+cu121' 'ultralytics==8.4.133' 'lap==0.5.12' 'numpy==1.26.4' 'opencv-python==4.10.0.84' 'pydantic==2.13.5' 'typer==0.27.2' 'pytest==9.1.1'
```

현재 실제 설치 환경의 지원 테스트 명령:

```bash
.omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-venv/Scripts/python.exe -m pytest -q tests/search/test_cv_lane_track_full_data.py tests/search/test_cv_lane_track_tracking.py
```

아래 명령은 기존 보존 manifest/resources/job을 입력으로 **새 출력**에 실행한다. SOURCE inventory 경로는 그대로 두며 새 manifest를 사용하려면 새 resource/job JSON의 입력 경로도 대응시킨다. 실행한 두 추적기는 아래와 동일하게 같은 job을 사용했다.

```bash
.omc/aihub-models/venv/Scripts/python.exe -m scripts.cv_lane_track_full_data .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/source_inventory.json .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic-repro/input
.omc/aihub-models/venv/Scripts/python.exe -m scripts.cv_lane_track_full_perception .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/V1-resources.json .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic-repro/perception/V1
.omc/aihub-models/venv/Scripts/python.exe -m scripts.cv_lane_track_full_perception .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/L3-resources.json .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic-repro/perception/L3
.omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-venv/Scripts/python.exe -m scripts.cv_lane_track_tracking_run ByteTrack .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/tracking_job.json .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic-repro/ByteTrack
.omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-venv/Scripts/python.exe -m scripts.cv_lane_track_tracking_run BoT-SORT .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic/tracking_job.json .omc/aihub-models/cv-lane-track-v1-2026-10-09/tracking-diagnostic-repro/BoT-SORT
```

후속 작업은 이 캐시를 이용한 동일 차선 경계의 시간 연결과 차량-경계 상대 위치 기반 교차 후보 생성이다. 이 진단으로 정확도 winner·사건 Recall@K·실선 위반을 확정할 수는 없다. 정량 정확도·최종 선정에는 별도의 검수된 GT가 필요하다.
