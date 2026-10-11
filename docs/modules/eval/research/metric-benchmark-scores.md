# 평가지표의 문헌 점수 — 그 지표로 다른 연구는 얼마나 나왔나

> **Owner:** 김대원 (`eval`) · **작성일:** 2026-10-03
> **성격:** research. 근거 문서이며 결정이 아니다.
> **짝 문서:** `metric-provenance.md`(지표가 **어느 문헌에서 왔나**). 이 문서는 그 문헌과 우리와 비슷한 연구에서 **그 지표가 몇 점이 나왔나**를 적는다.

---

## 0. 읽는 법 — 이 숫자들은 어떻게 모았나

팀 피드백(2026-10-02)에 따라, **초록이 아니라 본문 표에서 읽은 숫자만** 적는다.

- 각 숫자에는 출처 논문과 **표 번호**를 붙였다. arXiv PDF/HTML, CVF·학회 PDF, 공식 결과 페이지에서 표의 행을 직접 대조했다.
- 초록에만 근거한 숫자는 「**초록 기준**」, 원문을 열지 못한 것은 「**미확인**」으로 표시했다. 기억으로 채운 숫자는 없다.
- 영상이 **블랙박스(차량 탑재)**인지, **CCTV(고정 카메라)**인지, 다른 종류인지를 열로 따로 적었다.
- 조사 중에 요약 모델이 표를 잘못 읽은 사례가 두 번 나왔다.
  - ALPR(Laroca 2021) Table 9의 OpenALPR 열: 요약은 98.0·98.8, PDF 원문은 98.3·「−」
  - MAD 데이터셋의 최강 baseline: 요약은 CONE, 표 원문은 SOONet

  그래서 아래 숫자는 모두 PDF 원문을 기준으로 적었다. **초록이나 요약으로 종합한 보고서가 틀릴 수 있다는 실제 근거**다.
- 학교 도서관을 통해서만 받을 수 있는 유료 PDF는 이번에 열지 못했다(§6).

**가장 중요한 주의.** 문헌의 점수를 우리 점수와 **같은 잣대로 비교하면 안 된다.**
- 우리 candidate는 「대표 시점이 정답 onset ±2초 안」으로 판정한다. 문헌 대부분은 시간 IoU(tIoU)로 판정한다.
- 영상 길이, 질의 형태(자유 문장 / 고정 4종), 정답 수가 다르다.
- 아래 숫자는 「이 분야에서 어느 정도가 어려운 수준인가」를 가늠하는 **눈금**일 뿐이다.

---

## 1. 한눈에 — 우리 지표별 문헌 점수 범위

| 우리 지표 | 가장 가까운 문헌 과제 | 확인된 점수 범위 | 비교 가능성 |
| --- | --- | --- | --- |
| candidate `recall_at` (Recall@K) | 긴 영상 temporal grounding | **1시간 이상** 영상, R@1 tIoU0.5 = **4.1–5.6%**(MAD, 전용 학습 모델). R@10 = 12.8–19.0% | 판정식이 다르다(tIoU ↔ ±2초) |
| 〃 (Gemini 직접) | MLLM에 긴 영상을 통째로 넣어 구간 받기 | Gemini 성능은 길이에 따라 급락한다. Gemini-2.0-Flash IoU-AUC 49.2(<1분) → 2.9(>60분). 76분 평균 영상에서 Gemini-2.5-flash mIoU 0.053 | 우리 Coarse와 가장 비슷한 조건 |
| 〃 (top-K 후보 recall) | 검색 후 위치 찾기 2단계 | CLIP 후보 top-1/3/10 recall = 62.8 / 81.6 / 96.7% | hit 판정이 「±1–2.5분 창이 정답을 덮음」이라 매우 느슨하다 |
| `onset_error_sec` (초 단위 오차) | 사고 시점 찾기(CCTV) | VLM 평균 절대 시점 오차(MAE) 약 3.2초, 중앙값 +0.37초(충돌 **뒤** 프레임을 고르는 경향) | 초 단위라 가장 비슷하다. 다만 27초 짧은 클립 |
| `fp_per_clip` | TRECVID SED(CCTV) NDCR | 이벤트 대부분에서 최저 MinNDCR이 0.85–1.0. NDCR 1.0은 「아무것도 안 낸 시스템」과 같은 비용 | 개념(단위당 오경보)만 같다 |
| classification 위반 분류 | AI Hub 71555 공식 검증 | LRCN 위반상황 분류 F1 **0.8839** | 같은 데이터셋. 다만 클립이 아닌 이미지 분류다 |
| 위반 판정 (블랙박스, 타 차량) | DashCop(블랙박스, 이륜차) | 헬멧 위반 F1 65.6, 위반과 번호판 end-to-end F1 72.2 (P 84 / R 63) | 블랙박스로 타 차량 위반을 다룬 공개 연구는 이 1건뿐이다 |
| 위반 판정 (헬멧, CCTV) | AI City Challenge Track 5 | mAP 0.49(2024 1위) – 0.83(2023 1위) | CCTV라 블랙박스와 다르다 |
| plate `exact_accuracy` | ALPR end-to-end 인식률 | 차량 탑재·이동 영상(UFPR) **65–78%**, 정적·근접 촬영 95–99% | 판 단위 전체 일치 기준은 같다 |
| plate `abstention_recall` 계열 | selective classification | ImageNet top-5 위험 2% 이하일 때 커버리지 약 54–59% | 개념(기권 대 위험)만 같다 |

---

## 2. 우리가 인용한 문헌의 점수 (`metric-provenance.md` 참고문헌)

| # | 문헌 | 태스크 · 영상 종류 | 지표 | 보고된 점수 (표) |
| --- | --- | --- | --- | --- |
| 1 | TALL (Gao+ ICCV 2017) | 문장 → 영상 구간. **요리 영상**(TACoS), **연출된 실내 활동**(Charades-STA). 블랙박스·CCTV 아님 | R@n, IoU=m | Charades-STA (Table 2): CTRL R@1 IoU0.5 **23.63**, R@5 IoU0.5 58.92 / baseline VSA-STV 16.91, 53.89. TACoS (Table 1): CTRL R@1 IoU0.5 13.30 |
| 2 | DCASE 2016 Task 3 (Mesaros+ 2016 지표) | 실생활 녹음의 소리 이벤트 검출. **영상 아님** | segment ER·F1, event-based F1 (onset collar) | 공식 결과 1위 Adavanne: segment ER 0.8051 / F1 47.8%, event F1 **4.8%**. baseline: segment F1 34.3%, event F1 6.3%. event F1 최고 제출도 8.1%로 매우 낮다 |
| 3 | NIST TRECVID SED | 공항 **CCTV** 약 100시간(Gatwick) | NDCR = P_Miss + β·R_FA (1 = 출력 없음과 같음) | 2008 Table 1, 이벤트별 최저 **MinNDCR**: ElevatorNoEntry 0.0003, OpposingFlow 0.354, PersonRuns 0.851, Embrace 0.990, Pointing 1.000 |
| 4 | PASCAL VOC (Everingham+ IJCV 2010) | 정지 이미지 20클래스 검출. **영상 아님** | AP @ IoU>0.5 | 논문에 mAP 열이 없다. VOC2007 클래스별 최고 AP는 **9.4%(boat) – 43.2%(car)** (Table 6) |
| 5 | Laroca+ ALPR (IET ITS 2021) | 정지 이미지 번호판 검출·인식. 대부분 손에 든 카메라. **UFPR-ALPR만 차량 탑재·이동** | 번호판 전체 일치율 | Table 9: 제안 방법 8개 데이터셋 평균 **96.9%**(상용 Sighthound 87.8, OpenALPR 90.7). **UFPR-ALPR 90.0%**(Sighthound 62.3, OpenALPR 82.2) |
| 6 | Selective Classification (Geifman+ NeurIPS 2017) | 이미지 분류에 기권 옵션. **영상 아님** | 목표 위험도에서 위험·커버리지 | ImageNet ResNet50 top-5 (Table 6): 위험 1.89%, 커버리지 **59.4%**. CIFAR-10 (Table 1): 위험 0.92%, 커버리지 78.6% |
| 7 | OHEM (Shrivastava+ CVPR 2016) | 정지 이미지 검출. **영상 아님** | VOC mAP | VOC07 (Table 3): 67.2 → **69.9**(07 학습), 70.0 → 74.6(07+12 학습) |
| 8 | ICDAR 2019 ArT (1-N.E.D.) | 자연 장면 곡선 텍스트 인식. **영상 아님** | 1 − 정규화 편집거리 | 인식 1위 **85.32%** (CRAFT+TPS-ResNet), end-to-end 1위 54.91 (Table I) |
| 9 | Chow 1970, ISO/IEC 19795-1, Sokolova 2009, Datasheets 2021, Model Cards 2019 | 이론·표준·방법론 | — | **벤치마크 점수 없음** |

---

## 3. 비슷한 구조 — 긴 영상에서 무언가 찾기

| 문헌 | 영상 종류 · 길이 | 지표 | 점수 (표) | 우리와의 차이 |
| --- | --- | --- | --- | --- |
| **SnAG** (CVPR 2024, 2404.02257) | 영화 47–202분(MAD), 1인칭 3.5–20분(Ego4D-NLQ) | R@K, tIoU | MAD (Table 2) R@1 0.5: SnAG 5.55, SOONet 5.32, CONE 4.10. R@10 0.5: 19.00. Ego4D-NLQ (Table 1) R@1 0.5: 11.26 | 전용 학습 모델, 자유 문장 질의 |
| **Vidi** (2504.15681, ByteDance) | 일반 영상 428개, 1분 미만 – 60분 초과 | IoU 임계값을 훑은 AUC | Table 3, 길이 구간별 IoŪ. **Gemini-2.5-Pro: 42.6(<1분) → 9.9(10–30분) → 2.4(>60분)**. GPT-4o: 32.5 → 9.1 → 9.5. 전용 모델 Vidi-1.5: 58.4 → 38.1 → 32.3 | Gemini에 영상을 그대로 넣어 구간을 받는 조건이 우리 Coarse와 같다 |
| **ExtremeWhenBench** (2606.12300, 2026 프리프린트) | 평균 75.7분, 최대 9시간 | mIoU, top-K 후보 recall | Table 1 mIoU: Gemini-3.5-flash 0.115, Gemini-2.5-flash 0.053 (Charades에서는 0.308). Table 2: 검색 후 위치 찾기 2단계 0.354, 한 번에 넣기 0.053. Table 6: CLIP top-3 recall **81.6%** | 「탐색 실패 85% > 위치 실패 11%」. 우리 Coarse→Fine 구조를 뒷받침한다 |
| **CG-Bench** (2412.12075) | 10–80분, 근거 구간 평균 19초 | mIoU | Table 3: GPT-4o **5.62**, Gemini-1.5-Pro 3.95 | 질문형 질의 |
| **TimeScope** (2509.26360) | 3분 미만 / 3–10분 / 10분 초과 | R1@0.5 | Table 2: Qwen2.5-VL-7B 40.6 → 10.3 → 12.3, 전용 모델 46.3 → 42.3 → 37.8 | 10분을 넘으면 일반 MLLM이 급락한다 |
| **TimeLens** (CVPR 2026, 2512.14698) — 짧은 영상 대조군 | 평균 108초 | R1@0.5 | Table 1 Charades: **Gemini-2.5-Pro 61.1**, Gemini-2.5-Flash 56.1, GPT-4o 44.5 | 짧은 영상에서 Gemini가 강하다는 상한선 |
| VideoNIAH (ICLR 2025) | 10–180초 | QA 정답률 | Gemini 1.5 Pro retrieval 평균 90.7 | 「무엇」만 묻고 「언제」는 묻지 않는다. **위치 찾기 근거로 쓰면 안 된다** |

---

## 4. 같은 도메인 — 블랙박스·CCTV 사고, 위반, 번호판

### 4-1. 사고·도로 사건

| 문헌 | 영상 | 지표 | 점수 (표) |
| --- | --- | --- | --- |
| DAD (ACCV 2016) | **블랙박스**(대만, 678개) | AP | 원 논문 74.35% (Table 1). 후속 논문 프로토콜로는 DSA 48.1 → CRASH(2024) **65.3** |
| CCD / UString (ACM MM 2020) | **블랙박스**(YouTube 사고 + BDD100K) | AP / mTTA | CCD 99.5, A3D 94.4 (Table 2). **이미 포화** |
| DoTA (TPAMI 2022) | **블랙박스** 4,677개 | 프레임 AUC | 비지도 Ensemble 73.0, 지도 TRN 78.0 (Table 3). 타 차량끼리 이상(non-ego) 클래스별 65.2–77.5 (Table 4) |
| RoadSocial (CVPR 2025) | 소셜미디어 도로 영상(블랙박스 포함), 평균 35.6초 | 시간 위치 찾기 mAP@.3:.7 | Table 2: **Gemini-1.5-Pro 18.6**, GPT-4o 7.8, Qwen2-VL-72B 0.01 |
| VRU-Accident (ICCV 2025 WS) | **블랙박스** 사고 1,000개 | 객관식 정확도 | Table 4: Gemini 1.5-flash 66.9, 사람 전문가 94.7 |
| SafePLUG (2508.06763) | **블랙박스**(DoTA·MM-AU), 80–160프레임 | AP@50 | Table 3: 45.40. 사고 구간이 영상의 30–60%라 탐색 난이도가 낮다 |
| UCA (2309.13925) | **CCTV**(UCF-Crime), 평균 약 3.9분 | R@1 IoU0.5 | Table 4: MMN 4.66. 「R@1 IoU0.3은 모두 10% 미만」 |
| ACCIDENT@CVPR 2026 (2605.01512) | **CCTV** 2,027개, 중앙값 26.8초 | 시점·위치·유형 조화평균(ACCS) | Table 1: Gemini 3.1 0.473, 제안 방법 0.539, 사람 0.843. 시점 MAE 약 3.2초 |

### 4-2. 위반 탐지

| 문헌 | 영상 | 지표 | 점수 (표) |
| --- | --- | --- | --- |
| **AI Hub 71555** 교통법규 위반 상황 데이터 (공식 페이지) | **블랙박스**. 「스마트 국민제보로 경찰청에 신고되어 위반벌금이 집행된 데이터」 | 공식 유효성 검증 | ① 위반상황 분류 LRCN F1 **0.8839**(기준 0.8). ② 시설물 bbox mAP 92.62%. ③ 영역 세그멘테이션 mAP@0.5 92.34%. ④ 차선 폴리라인 mAP 91.57%. **위반 차량 지정과 번호판 성능은 공개되지 않았다** |
| **DashCop / RideSafe-400** (2503.00428) | **블랙박스**(DDPAI X2S Pro, 1080p) 영상 400개 | P / R / F1 | 헬멧 위반 F1 **65.63** (Table 3). 위반 판정과 번호판 전체 일치를 모두 맞춰야 하는 e-ticket F1 **72.18** (P 84.21 / R 63.16, Table 2) |
| AI City Challenge Track 5 (헬멧) | **CCTV**(인도 교통 카메라) | mAP | 2023 1위 **0.8340**, 2024 1위 0.4860 (혼잡·줌 장면이 추가됨) |
| 선민수 외, 한국컴퓨터정보학회논문지 2025 | 엣지 디바이스(카메라 종류 **미확인**) | P / R | **초록 기준** 83.3 / 71.4 |

> 신호위반·중앙선침범·실선 진로변경을 **블랙박스로 정량 평가한 공개 벤치마크는 찾지 못했다.**

### 4-3. 번호판 인식

| 문헌 | 영상 | 점수 (표) |
| --- | --- | --- |
| UFPR-ALPR (IJCNN 2018) | **차량 탑재·이동** (블랙박스와 가장 비슷) | end-to-end 프레임 단위 **64.89%**, 여러 프레임을 합치면 78.33% (Table VI) |
| Cross-dataset LPR (VISAPP 2022) | UFPR(차량 탑재), RodoSol(**요금소 고정**) | UFPR 최고 78.3%, RodoSol 59.6% (Table 5). 학습에서 뺀 데이터셋으로 평가하면 71.3%, 47.8% (Table 6) |
| DashCop 번호판 OCR | **블랙박스**, 이륜차 | CRNN **85.71%** (Table 7, OCR 단계 단독). Google OCR 33.34% |
| CCPD (ECCV 2018) | 주차 단속원 휴대 단말 | 인식 정밀도 Base 98.5, Challenge 85.1 (Table 5) |
| 한국 번호판 W-LPR (Sensors 2021) | 주차장·정적 촬영(KarPlate, 촬영 방식 **미확인**) | end-to-end **98.94%** (Table 5) |

> 한국 번호판 99%는 정적 조건의 수치다. **블랙박스 이동 조건의 기대치는 65–86% 구간이 더 현실적이다.**

---

## 5. 우리 베이스라인과 나란히 놓으면 (참고용, 같은 잣대가 아니다)

> 같은 잣대(문헌 방식)로 우리 예측을 다시 잰 비교는 `baselines-vs-literature.md`에 있다. 아래 표는 공식 지표를 그대로 나란히 놓은 참고용이다.

| 우리 측정 (2026-09-28 – 10-01) | 문헌 눈금 | 읽는 법 |
| --- | --- | --- |
| Gemini Coarse, b_youtube 123클립(10이벤트): Recall@1 0.10, **Recall@3 0.50**, 위치만 맞힘(@3) 0.70 | 1시간 이상 영상에서 R@1 tIoU0.5는 4–6%(전용 모델). Gemini는 60분 초과에서 IoU-AUC 2–3 | 판정이 ±2초 onset이고 클립을 잘라 넣어서 문헌과 바로 비교할 수 없다. 사건 10개라 95% 신뢰구간은 약 0.24–0.76이다 |
| Gemini 오탐: 음성 클립당 2.8개 | TRECVID SED 대부분 이벤트의 MinNDCR 0.85–1.0 | 오탐은 감시 영상 검출에서도 가장 큰 병목이다 |
| readout 번호판(사전학습 인식기), m2 314장: 판독한 것 중 정확 일치 **0.431**, 확정했는데 틀림 22.1% | 블랙박스·이동 촬영 65–86%, 정적 촬영 95–99% | 문헌 대비 낮다. 다만 우리는 AI-Hub 크롭이고 기권을 허용한다 |

---

## 6. 기존 문서 정정과 미확인 목록

### `metric-provenance.md`에서 고칠 것
- §2-2: 「DCASE 2016 기준 onset ±200 ms」 → 공식 채점 원문은 **t_collar = 0.250 s(250 ms)**다. Mesaros 2016 원문의 200 ms 표기는 원문을 열지 못해 확인하지 못했다.
- §2-6: VOC는 「임계값 0.5」 근거로는 맞다. 다만 IJCV 2010 논문에는 mAP가 없고 클래스별 AP만 있다(인용할 때 주의).

### 도서관 PDF로 확인해야 할 것
1. Mesaros+ 2016 원문: collar 정의 (MDPI·저장소 모두 접근 실패)
2. TRECVID SED의 이벤트별 **Actual** NDCR (2012 이후 그림에만 있다)
3. 선민수 외 2025(KCI): 카메라 종류, 시험셋 규모
4. 최민성·문미경 2023(KCI): 블랙박스 진로변경 탐지 수치
5. KarPlate 촬영 방식, DashCop 게재처, CG-Bench·UCA 게재처
6. 열지 않은 것:
   - MAD 원 논문
   - LV-Haystack(T\*): 요약만 봄
   - TUMTraffic-VideoQA
   - TimeLens2
   - Gemini 2.5 기술보고서의 Charades-STA 수치
   - MM-AU·DADA-2000·A3D 원 논문
   - DoTA Table 5 분류 정확도 31.0%: 요약만 봄
7. AI Hub 71555 ②·④의 IoU 기준, 위반 유형별 개별 성능 공개 여부

---

## 참고 URL (실제로 연 원문)

- TALL https://arxiv.org/pdf/1705.02101 · DCASE2016 결과 https://dcase.community/challenge2016/task-sound-event-detection-in-real-life-audio-results
- TRECVID SED https://www.nist.gov/system/files/documents/itl/iad/mig/NIST_WMVC_2009.pdf · https://www-nlpir.nist.gov/projects/tvpubs/tv12.papers/tv12overview.pdf
- VOC http://host.robots.ox.ac.uk/pascal/VOC/pubs/everingham10.pdf · ALPR https://arxiv.org/pdf/1909.01754
- Selective https://arxiv.org/pdf/1705.08500 · OHEM https://arxiv.org/pdf/1604.03540 · ArT https://arxiv.org/pdf/1909.07145 · RCTW-17 https://arxiv.org/pdf/1708.09585
- SnAG 2404.02257 · TimeLens 2512.14698 · ExtremeWhenBench 2606.12300 · TimeScope 2509.26360 · Vidi 2504.15681 · CG-Bench 2412.12075 · VideoNIAH 2406.09367 · RoadSocial (CVF CVPR 2025) · SafePLUG 2508.06763 · UCA 2309.13925 · ACCIDENT 2605.01512
- DAD https://yuxng.github.io/Papers/2016/chan_accv16.pdf · UString 2008.00334 · CRASH 2407.17757 · DoTA 2004.03044 · VRU-Accident 2507.09815 · AccidentBench 2509.26636
- AI City 2304.07500 · 2404.09432 · DashCop 2503.00428 · AI Hub https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71555
- UFPR-ALPR 1802.09567 · Cross-dataset LPR 2201.00267 · CCPD (ECCV 2018 CVF) · W-LPR https://pmc.ncbi.nlm.nih.gov/articles/PMC8233874/
- KCI 선민수 외 2025 https://www.kci.go.kr/kciportal/landing/article.kci?arti_id=ART003204575
