# 차선·차량 인식과 위반 설명 테스트 통합 기록

2026-10-10 · PR #338 문서 추가 · 실행 결과와 미평가 항목을 구분한 요약

이 문서는 AI Hub 결과 확인 → 2fps 표시 영상 → 실선·점선 모델 → Gemini 프롬프트 변경 → 다른 실선 영상 확장 → 전체 사용자 힌트 실험을 한 흐름으로 정리한다. 별도로 진행한 차량·차선 모델 비교, 추적·교차 후보와 라벨 준비도 연결한다. 기존 Coarse/Fine 실험은 관련 보고서를 참조한다. 새 제품 파이프라인 배포나 위반 확정 기능 구현 결과가 아니다.

## 1. AI Hub 모델에서 확인한 것

15개 개발 영상은 총 645.658초, 위반 12영상·정상 3영상이며 사건 13건(신호2·중앙선2·실선 변경9)이다. 공간 모델 8종에 동일 651프레임(1fps)을 입력해 5,208프레임 추론했고 LRCN 장면 분류도 실행했다.

- 객체 모델은 차량·신호등 등 위치를 출력한다. 파일명에 위반 유형이 있어도 위반 차량을 구별하는 검출기는 아니다.
- 백색 차선 모델의 클래스는 `white_solid`이며 점선 클래스가 없다. 합법 점선 영상 141956의 10초 경계를 `white_solid` 0.99로 덮었다. 점선 사이를 연속 마스크로 메우는 출력도 있어 confidence를 실선 확정 근거로 사용할 수 없다.
- LRCN은 신호·중앙선·진로변경 3클래스만 있다. 전체 영상 종류 분류 10/12, 정답 사건 주변 종류 10/13이지만 정상 3/3도 위반 종류를 출력했다. 정상 창 confidence≥0.8도 24/24라 정상 필터로 검증되지 않았다.
- 사건 구간 어딘가에 `white_solid`가 나온 9/9는 위반 차량이 그 선을 넘었다는 결과가 아니다. 차량·선·시각을 연결하는 단계가 필요하다.

근거: [AI Hub 9종 실영상 평가](aihub-model-video-2026-10-04.md). 초기 비교 이미지와 1fps 주석 영상 3개도 로컬에 존재한다.

## 2. 2fps 차선·차량 표시 영상

사용자 요청으로 141927 교량 영상의 시작부터 20초를 **원본 2fps, 40개 관측**으로 다시 추론했다. AI Hub YOLOv5 신호위반 가중치의 차량 검출과 백색 차선 Mask R-CNN을 사용했다. 표시 confidence≥0.8, 예측 저장≥0.25, RTX3060 실행이다. 2fps는 관측·추론 밀도이며 재생 컨테이너 fps와 구별한다.

파일은 `.omc/aihub-models/overlay-2fps-2026-10-10-bridge-solid-v2/bridge-solid-2fps.mp4`, 근거는 같은 폴더 `manifest.json`, `predictions.jsonl`, `qa-preview.jpg`다. 원본 영상·프레임 인덱스·두 가중치 해시를 manifest에 보존했다. 이 영상에서도 모델에 점선 클래스가 없다는 문제가 해결되지는 않았다.

## 3. UFLD와 실선·점선 모델의 역할

**UFLD는 Ultra Fast Lane Detection이다.** 이번 실행은 UFLDv2 ResNet34 CULane이며 차선의 위치 곡선을 출력한다. 현재 adapter에는 도색 색상, 실선/점선, 중앙선 역할, confidence가 없다. 표시 곡선이 이어져 있다는 이유로 실선이라고 판단하지 않고 의미는 UNKNOWN, confidence는 null이다.

별도로 실선·점선 클래스가 있는 **PP-LiteSeg `pp_lite_stdc2_bdd100k`**를 실행했다. background·double_yellow·solid·dashed 4클래스를 유지하고, 공식 예시의 dashed 제거 후처리는 사용하지 않았다. 교량 실선 141927과 합법 점선 141956의 첫 20초를 각 2fps/40관측, 총 80장 처리했다. 원본 1920×1080, CPU FP32 평균 약2.25초/장으로 2fps 실시간 처리 결과는 아니다.

표시 색은 초록 solid·분홍 dashed·노랑 double_yellow다. 표시 색과 실제 도로 페인트 색은 다르다. 합법 점선 영상의 10초 오른쪽 경계에서 dashed를 확인했지만 같은 경계에 종류가 섞이고, 교량 철골·난간·보닛 등에 오탐이 있다. 정밀 mask GT가 없어 유형 정확도나 mIoU는 계산하지 않았다.

근거: [PP-LiteSeg 실선·점선 진단](pp-liteseg-solid-dashed-2026-10-10.md), [UFLDv2/AI Hub 차선 비교](cv-lane-model-comparison-2026-10-09.md).

## 4. Gemini 입력·프롬프트 변화와 결과

목표 구조는 ‘사건 종류를 미리 알려 준 뒤 차선 표시 영상을 보내 차량·선 횡단을 설명하게 하기’다. 초기에는 종류만 알고 위반 존재·대상 차량·시각은 알려 주지 않았다. 마지막 실험에서만 전체 정답지와 파일명을 사용자 힌트로 제공했다. 종류를 정해 주는 것과 영상에서 발생 사실이 이미 확정된 것은 구분한다.

이 묶음은 요청·실제 응답 모델 `gemini-3.8-flash`, reasoning low, 최대 출력2,000토큰, 자동 재시도0을 사용했다. 초기 출력4,096 요청의 HTTP400 2회는 별도 오류이며 성공 호출 수에 넣지 않는다. 원본 2fps 관측을 0.5배속 API 영상으로 전달했다. 인코딩 프레임 반복은 새 관측이 아니다.

| 순서 | 입력·주요 변경 | 범위 / 성공 호출 | 결과 | 상세 |
|---|---|---|---|---|
| 1 | 원본만 vs 원본+차선 표시, 상세 검증·JSON | 141927 20초 / 3+3회 | 두 조건 모두 0/3, NOT_OBSERVED | [종류 지정 A/B](gemini-lane-overlay-known-type-2026-10-10.md) |
| 2 | 표시본만, 짧은 자유 서술; 실제 페인트 색·단일/이중 확인 항목 제거 | 같은20초 / 3회 | 0/3, 모두 변경 없음 | [짧은 프롬프트](gemini-lane-overlay-only-short-prompt-2026-10-10.md) |
| 3 | 초록선이 차량 옆→하단→반대편으로 바뀌는 과정 추가 | 같은20초 / 3회 | 3/3 양성이나 모두 다른 흰 SUV, 정답 차량0/3 | [초록선 묘사](gemini-green-line-crossing-description-2026-10-10.md) |
| 4 | 같은 프롬프트를 다른 실선 영상 하나에 적용 | youtube_clip_01 전체5.533초 / 3회 | 흰 세단 왼쪽→ego 이동3/3 부합. 응답1.5–3.5/4초는 기존GT0–2보다 늦게 종료 | [추가 한 영상](gemini-green-crossing-second-clip-2026-10-10.md) |
| 5 | 남은 실선 6영상 전체 적용, 종류만 제공 | 각60초 / 18회 | 양성9/18, 차량·행위·GT구간 부합1/18(C10). 7사건×3회의 부합1/21 | [남은 영상 전체](gemini-green-crossing-remaining-2026-10-10.md) |
| 6 | 같은6영상에 전체 정답지+파일명 추가 | 같은60초 / 18회 | 양성18/18, 제공된7사건 모두3회씩 긍정. 일부 잘못된 대상·미확인 완료 서술 | [전체 힌트](gemini-overlay-full-user-hints-2026-10-10.md) |

성공 응답은 총 **51회**(6+3+3+3+18+18)다. 전체 힌트 추가도 실행 완료 결과다. 모델 설정을 고정했지만 1→2는 영상 개수·프롬프트·응답 형식을 함께 바꿨으므로 효과를 따로 추정할 수 없다. 작은 개발 표본의 반복이며 각 회차를 독립 사건으로 세지 않는다.

초기 JSON 시각은 API 재생 시각에0.5를 곱해 원본으로 환산했다. 이후 자유 서술은 화면 `t=`의 원본 시각으로 답하도록 했으므로 추가 환산하지 않았다. 25fps 원본의 관측은 0.48/1.52초 등 실제 프레임 시각을 기록한다. 6영상은 각각120관측으로 총720개이며 1280×720 API 표시본으로 전달했지만 원본640×360의 정보량이 늘어난 것은 아니다.

### 프롬프트 선택에 따른 관찰

‘선 정보가 확실하다’는 취지는 짧은 프롬프트의 **“영상에 표시된 차선 정보를 판단 기준으로 사용하세요”**에 반영했다. 별도로 차선 GT를 확정하거나 표시를 보정하지 않았다. 초기 1·2번의 도색 색·단일/이중 항목은 이후 제거했고 표시 색의 범례만 남겼다. 전체 정답지 제공은 사용자가 모든 힌트를 준다고 가정한 별도 마지막 조건이므로 정답지 원문의 도색 정보까지 포함한다.

같은 차량이 같은 경계를 넘는 전후 관계는 시각·종류만 전달하는 것과 다르다. 초록선 횡단 묘사는 양성 응답을 만들었지만 141927에서는 실제 대상인 짙은 SUV 대신 흰 SUV를 지목했다. 전송본에서 불안정한 초록 표시가 흰 SUV와 겹치는 것도 관찰됐다. 차량 밑에 마스크가 그려진 한 순간만으로 실제 횡단을 확인할 수 없었다.

전체 힌트 조건에서 C05 첫 사건과 C10은 각3회의 차량·방향·대략적 구간이 부합했다. C09는 왼쪽 택시를 지목했고 C39·C47·C44의 주장한 진입 완료는 검수 화면이 뒷받침하지 않았다. C05 두 사건을 같은 차량으로 연결한 것도 미확인이다. 모든 응답이 정답 사건을 긍정해도 시각 복창과 시각적 근거 확보를 구별해야 한다. 영상 없는 정답지 대조는 실행하지 않았다.

## 5. 영상·이미지 보존 위치

아래는 **저장소 루트 기준 로컬 파일**이다. GitHub에 업로드한 미디어 링크가 아니며 `.omc` 파일은 PR에 포함하지 않는다. 표시 영상·원본 대조 이미지가 존재하는 것을 확인했다.

| 자료 | 로컬 위치 |
|---|---|
| 초기 AI Hub 비교 이미지 / 1fps 영상 | `.omc/aihub-models/run/evidence/comparison.jpg`, 같은 폴더 `{bridge-solid,legal-dashed,signal-red}.mp4` |
| AI Hub 차선·차량 2fps 영상 / 미리보기 | `.omc/aihub-models/overlay-2fps-2026-10-10-bridge-solid-v2/{bridge-solid-2fps.mp4,qa-preview.jpg}` |
| PP-LiteSeg 실선·점선 영상 | `.omc/pp-liteseg-lane-2026-10-10/{bridge-solid-pp-liteseg-2fps,legal-dashed-pp-liteseg-2fps}.mp4` |
| 최초 Gemini 원본/API 대조 | `.omc/gemini-lane-overlay-2026-10-10/api-input-review.jpg` |
| 표시본만 짧은 프롬프트 결과 | `.omc/gemini-lane-overlay-only-2026-10-10/` |
| 141927 초록선 묘사 대조 | `.omc/gemini-lane-green-crossing-2026-10-10/` |
| 추가 한 영상 대조·영상 | `.omc/gemini-green-crossing-second-clip-2026-10-10/` |
| 남은6영상·원본/API 대조 | `.omc/gemini-green-crossing-remaining-2026-10-10/<영상ID>/{overlay-2fps.mp4,overlay-api-half-speed.mp4,target-review.jpg}` |
| 전체 힌트 프롬프트·18응답·집계 | `.omc/gemini-all-hints-2026-10-10/`(입력 미디어는 직전 폴더 재사용) |

초기 차선 표시본 일부에는 음성이 있으나 Gemini 입력에서는 음성을 제거했다. 자료별 manifest·예측·대조 시트를 함께 보존하며 모델 출력 이미지를 정답 mask로 취급하지 않는다.

## 6. 차량·차선·추적 및 교차 후보 후속 테스트

이 경로는 Gemini 표시 실험과 별개인 CV_LANE_TRACK 개발 진단이다. 같은15영상에서 모델 비교는 1,200프레임, 전체 추적·후보는5fps/3,233프레임을 사용했다. 2fps 표시 실험과 혼합하지 않는다.

| 단계 | 완료된 실행·결과 | 제한·상세 |
|---|---|---|
| 차량7종 | 1,200프레임×3회×7종,25,200행. V1 AIHubYOLO adapter p50/p95 10.54/15.06ms | bbox·ID GT 없어 정확도 순위/최종 선정 없음. [차량 비교](cv-vehicle-model-comparison-2026-10-09.md) |
| 차선2종 | L1 AIHub 백색+황색 / L3 UFLDv2 각3회,7,200행. p50/p95 195.45/305.14 vs51.42/90.30ms | CLRerNet는 환경 차단으로 추론 미실행. PP-LiteSeg CPU 속도와 공정 비교 아님. [차선 비교](cv-lane-model-comparison-2026-10-09.md) |
| 두 추적기 | 임시V1+L3 캐시,ByteTrack/BoT-SORT,15영상 전체 | 관측 수·ID개수는 추적 정확도 아님. [추적 진단](cv-tracking-diagnostic-2026-10-09.md) |
| 최초 교차 후보 | ByteTrack2+BoT-SORT3=5후보,화면3구간(C00/C33/C10) | 같은 사건의 추적기별 중복. 전부UNKNOWN/score null. [최초 후보](cv-crossing-candidates-2026-10-10.md) |
| 안정화v2 | 5→2후보,C00약13.50초 같은 구간을 두 추적기가 제안 | 보정 성공 증가·차선 연결 감소. 작은/경계bbox보류가 원거리 사건도 숨길 수 있음. [안정화](cv-crossing-stability-2026-10-10.md) |
| 보정·연결 후속 | 유사 변환 우선/full 보완: 실패763→656,연결차선5,058→5,366,새ID2,687→2,379. C00두 후보 유지 |8조합 효과분리·접지보호 민감도 진단,28테스트 통과 기록. 일반 정확도 개선 아님. [연속성](cv-crossing-continuity-2026-10-10.md) |
| 라벨 준비 | 원본1,200장/29작업,초안bbox7,405·곡선3,924,첫검수174장,26테스트 통과 기록 | 자동초안·정답검수 미완료.CVAT실서버업로드 미검증. [라벨 준비](cv-label-preparation-2026-10-10.md) |

전체 현황은 [CV 진행 요약](cv-lane-track-progress-summary-2026-10-10.md)에 정리했다. 위 테스트 수는 해당 실행 당시 기록이며 이번 문서 추가 중 모델 추론·제품 테스트를 다시 수행했다는 뜻이 아니다. 로컬 구현·캐시·라벨 ZIP은 이 문서 PR에 포함하지 않는다. 기존 사건 종류·구간 정답은 재사용하며 부족한 차량·차선 좌표와 ID를 보충해야 한다.

## 7. 관련 Coarse/Fine·모델 테스트 기록

기존 결과를 덮어쓰지 않고 아래 문서와 [전체 실험 색인](README.md)에 연결했다.

- [AI Hub 공간 Coarse+sol Fine](aihub-coarse-sol-fine-2026-10-04.md):63후보,최종 정답 구간 중첩2/13,정상3/3기각.
- [AI Hub LRCN+sol Fine](aihub-lrcn-sol-fine-2026-10-04.md):51후보,정답 구간·종류 중첩4/13. 조건 차이와1회 실행으로 우월성 미확정.
- [AI Hub+sol 토큰 분석](aihub-sol-token-analysis-2026-10-04.md):기존 기록 분석,새 호출 없음.[후속 예산 설계](aihub-sol-budgeted-design-2026-10-04.md)는 미실행 제안.
- [Fine 고정 구간·불확실성](gemini-fine-window-uncertain-2026-10-01.md),[crop×대상 힌트](gemini-fine-crop-hint-2026-10-01.md),[Coarse4fps](gemini-coarse-4fps-2026-10-02.md):141927의 대상 연결·선 판단 실패를 확인한 이전 비교.
- [sol Fine 해상도·구간 폭](gpt-sol-fine-resolution-window-2026-10-02.md),[sol Fine720 파이프라인](search-v3-gpt-sol-fine720-2026-10-02.md),[set1 확장](search-v3-gpt-sol-fine720-set1-2026-10-04.md):고정 구간 결과와 전체 후보 검출 결과의 차이를 기록.
- [Flash 유형1개vs4개](search-flash-set1-event-types-2026-10-09.md):A최종2·1·1/11,B0·0·0/11,반복한 개발 표본의 차이.[유형별B-split](search-flash-set1-split-coarse-2026-10-10.md)은1회top3 2/11·Coarse5/11,비용약2.5배.
- [VideoChat3-4B RTX3060 사전검증](videochat3-window-preflight-2026-10-10.md):93창×3유형×2질문,판단용Recall@3 1/11,무작위95백분위 이하. 큰GPU실험은 미진행.
- [Retrieval Coarse 사전검증](retrieval-coarse-preflight-2026-10-11.md)·[v2](retrieval-coarse-v2-2026-10-11.md):SigLIP 프레임·문장 유사도. v1 판단용Recall@3 4/11(약한 신호, 적중 절반이 신호위반), v2·차선 표시 프레임 점검은 신호 부족. 차선 위반의 「선 위에 걸친 차」를 정상 주행과 구분하지 못함. 영상 임베딩 [Qwen3-VL-Embedding](retrieval-coarse-qwen3vl-embedding-2026-10-12.md)·[차선 표시 입력](retrieval-coarse-qwen3vl-overlay-2026-10-12.md)도 신호 부족이라 retrieval Coarse는 정리.

## 8. 이번 문서화의 검증 범위

실험 report·manifest·완료 응답·토큰 합계·입력 파일 해시와 대조 이미지를 확인해 정리했다. 신규 Markdown의 상대 링크와 표·프롬프트 구분을 검사한다. 원시 JSON/JSONL,영상,API 키를 이 PR에 추가하지 않는다. 독립 정상·위반 검증 데이터와 정밀 대상·차선 GT 평가,운영 Search 통합은 남아 있다. 정답지 제공 실험에서의 양성 증가를 자동 검출 성능으로 발표할 근거는 없다.
