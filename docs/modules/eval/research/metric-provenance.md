# 평가지표의 출처 — 어느 문헌에서 왔고, 무엇이 우리 것인가

> **Owner:** 김대원 (`eval`) · **작성일:** 2026-09-16
> **성격:** research. 근거 문서이며 결정이 아니다(`docs/README.md` 「Research는 근거이지 결정이 아니다」).
> **이 문서는 지표를 정의하지 않는다.** 정의의 소유자는 `architecture/module-architecture.md` §9-3 와
> `modules/eval/initial-evaluation-plan.md` §2 이고, 계산 규칙의 실물은 `eval/scorers/*.py` 다.
> 여기 적힌 식은 대조를 위한 **요약**이며, 어긋나면 위 문서와 코드가 이긴다.
> **짝 문서:** 그 문헌에서 지표가 실제로 몇 점이 나왔는지는 `metric-benchmark-scores.md`(2026-10-03).

---

## 0. 먼저 — 이 문서는 사후 대조표다

정직하게 적는다. **우리는 논문을 읽고 지표를 고른 것이 아니다.** v4 §9-3 의 지표 목록은
제품이 약속한 것(「후보를 Top-3 안에 올린다」·「모르면 모른다고 한다」)에서 역산해 정해졌고,
레포 어디에도 인용은 없었다.

이 문서가 하는 일은 그 다음이다 — **이미 정한 지표가 어느 측정 전통에 서 있는지를 사후에 맞춰 보고,
그 전통이 그 지표를 왜 그렇게 정의했는지를 확인해 우리 정의의 빈틈을 드러내는 것.**
그래서 3절(문헌에 없는 것)과 4절(문헌을 따르지 않기로 한 것)이 이 문서에서 가장 쓸모 있는 부분이다.

「이 지표는 X 논문에서 차용했다」고 대외적으로 말하려면 이 문서의 **2절 「대응 강도」 칸이
`직접 대응`인 항목만** 그렇게 말할 수 있다. `느슨한 유비`·`우리 정의`는 그렇게 말하면 거짓이 된다.

---

## 1. 한눈에 보기

| 지표 | 단계 | 문헌 전통 | 대응 강도 |
| --- | --- | --- | --- |
| `recall_at` (Recall@1/3/10) | candidate | IR 의 Recall@K → 영상 moment retrieval 의 `R@n, IoU@m` (Gao+ 2017) | 직접 대응 (판정식만 교체) |
| `onset_error_sec` + `tolerance_sec` | candidate | 이벤트 검출의 onset tolerance / collar (Mesaros+ 2016, DCASE) | 직접 대응 |
| `containment_rate` | candidate | — | **우리 정의** |
| `fp_per_clip` / FP-per-hour | candidate | NIST TRECVID SED 의 R_FA(단위시간당 오경보), NDCR = P_Miss + β·R_FA | 직접 대응 (분모만 clip) |
| `recall_macro` / `precision_macro` | classification | macro-averaging (Sokolova & Lapalme 2009) | 직접 대응 |
| 5×5 confusion (4종 + `NONE`) | classification | 검출 평가의 background/negative class 관례 | 느슨한 유비 |
| `target_correctness` (bbox IoU ≥ 0.5) | classification | PASCAL VOC 의 overlap criterion (Everingham+ 2010) | 직접 대응 (임계값 포함) |
| `exact_accuracy` | plate | ALPR 의 end-to-end recognition rate (Laroca+ 2021) | 직접 대응 |
| `wrong_accept_rate` | plate | 생체인식의 False Accept Rate (ISO/IEC 19795-1) | 느슨한 유비 (**분모가 다르다**) |
| `abstention_recall` | plate | reject option / selective classification (Chow 1970; Geifman & El-Yaniv 2017) | 느슨한 유비 |
| CER (진단용, 미구현) | plate | ICDAR Robust Reading 의 normalized edit distance | 직접 대응 |
| Hard-negative FPR (미구현, F4) | fine | hard example mining (Shrivastava+ 2016) | 느슨한 유비 |
| `cost_per_case` / `cost_per_source_video_hour` | efficiency | — | **우리 정의** |
| `coverage` · null 규율 | 전 단계 | 데이터셋·모델 문서화 규범 (Gebru+ 2021; Mitchell+ 2019) | 방법론 유비 |

---

## 2. 지표별 — 무엇을 차용했고 우리는 무엇을 바꿨나

### 2-1. `recall_at` — Recall@K

**요약식.** 사건 하나가 상위 K개 후보 중 하나에라도 맞으면 적중. 분모는 **사건 수**(클립 수가 아니다).

**차용.** Gao 등의 TALL(ICCV 2017)이 쓴 `R@n, IoU@m` — 「상위 n개 결과 중 적어도 하나가 정답과
IoU > m 이면 성공」. 우리 `recall_at` 은 이 정의의 n(=K)만 그대로 쓰고 **판정식을 교체**했다.
전통 자체는 더 오래된 IR 의 Recall@K 이지만, 「시간축 위에서 구간을 랭킹해 상위 K를 본다」는
우리 문제와 같은 모양을 먼저 쓴 것은 moment retrieval 쪽이다.

**왜 이 전통인가.** 제품 약속이 「사용자가 검토할 후보를 짧게 준다」이므로, 정확도가 아니라
**랭킹의 상위 K 안에 정답이 들어오는가**가 측정 대상이다. K를 1/3/10으로 둔 것은 UX 상의
검토 부담 구간(1건만 본다 / 3건 본다 / 10건까지 본다)과 맞춘 것이고 문헌에서 온 값이 아니다.

**우리가 바꾼 것 — 왜 tIoU 를 버렸나.** 문헌은 예측 구간과 정답 구간의 **시간 IoU** 로 판정한다.
우리는 계약 v1.1 §4-1 이 `span` 을 「coarse 후보 창」으로 확정한 순간 이 판정을 버렸다 —
창은 모델이 정답 구간을 주장한 값이 아니라 **더 볼 구간을 제안한 값**이라, 창을 넓게 잡으면
IoU 는 떨어지는데 제품 품질은 나빠지지 않는다. 그래서 **onset 지점 오차 ≤ tolerance** 로 바꿨다
(`eval/scorers/candidate.py`, `SCORER_VERSION = "s2"`). 창의 품질은 `containment_rate` 로만 남겼다.

**문헌과 같아진 부분 (F7 해소, 2026-09-16 `s3`).** 문헌의 Recall@K 구현은 보통 매칭된 예측을
소비(1:1 배정)한다. 우리도 이제 클립 단위 **최대 매칭**으로 배정한다 — 그 전에는 사건마다 독립으로
훑어서 한 예측이 적중 2건으로 세어질 수 있었다. 탐욕이 아니라 최대 매칭을 쓰는 이유는 recall 이
정답지의 사건 나열 순서에 휘둘리지 않게 하기 위해서다. 다만 **순서 무관은 recall 에만 해당한다** —
매칭의 크기는 유일해도 어느 쌍으로 맺는지는 유일하지 않아, 쌍을 쓰는 `onset_error_sec`·
`containment_rate` 는 배정 순서를 따로 고정해야 했다(`harness-v1-design.md` §9 F7).

### 2-2. `onset_error_sec` · `tolerance_sec` — onset 허용오차

**요약식.** 적중한 예측의 대표 시점과 GT onset 의 절대오차. 표본은 예측 수가 아니라 **적중한 사건 수**.

**차용.** Mesaros·Heittola·Virtanen, *Metrics for Polyphonic Sound Event Detection*(Applied Sciences 6(6):162, 2016)
및 DCASE 의 event-based metrics — 검출 이벤트가 정답과 같은 이벤트인지를 **onset 에 collar(허용오차)를
두고** 판정한다. DCASE 2016 Task 3 공식 채점의 onset collar 는 **250 ms**(`t_collar=0.250`)다.
흔히 인용되는 「±200 ms」는 Mesaros 2016 원문을 열지 못해 확인하지 못했다(2026-10-03, `metric-benchmark-scores.md` §6).

**왜 이 전통인가.** 이 분야가 우리와 같은 문제를 먼저 풀었다 — 정답 구간의 **끝(offset)은 라벨러마다
흔들리지만 시작(onset)은 비교적 단단하다.** 그래서 offset 에는 느슨한 규칙을 주거나 아예 빼고
onset 중심으로 판정한다. 블랙박스 위반 사건도 똑같다: 「신호위반이 언제 끝났나」는 사람마다 다르고
「정지선을 넘은 순간」은 거의 같다.

**우리가 바꾼 것.** 허용오차를 250 ms 가 아니라 **2.0초**로 뒀다(`DEFAULT_TOLERANCE_SEC`).
음향 이벤트와 달리 우리 라벨 단위는 초 단위 사람 판독이고, 후보의 대표 시점은 창의 대표값이지
검출 순간이 아니기 때문이다. **이 값은 문헌 근거가 없는 우리 선택이며, B tier 사건의 span 라벨
폭 편차를 재서 정해야 한다**(F8).

### 2-3. `fp_per_clip` — 단위당 오경보

**요약식.** 사건 없는(negative) 클립에서 나온 후보 개수 ÷ negative 클립 수. 사건 있는 클립은 분모에 없다.

**차용.** NIST TRECVID **Surveillance Event Detection** 의 `R_FA`(단위시간당 오경보 수)와
`NDCR = P_Miss + β·R_FA`. 검출 과제에서 오탐을 precision 으로 재지 않고 **단위시간(또는 단위입력)당
절대 건수**로 재는 관행이 여기서 왔다.

**왜 이 전통인가.** 긴 영상에서 사건은 희소하다. precision 은 사건 밀도에 따라 같은 시스템이
다른 값을 받지만, 「1시간 돌리면 헛것을 몇 번 보여주나」는 밀도와 무관하게 사용자가 겪는 비용
그대로다. v4 §9-3 이 「FP/hour 또는 FP/clip — dataset 성격에 맞게 raw duration 과 함께 보고」라고
둘을 병기하게 한 것도 같은 이유다.

**우리가 바꾼 것.** 분모를 시간이 아니라 **negative 클립 수**로 뒀다. B tier 의 `YT_0002` 는 20초
원본에서 나온 조각 1개뿐이고 그 조각에 위반이 있어 negative 가 없다 — 그래서 `fp_per_clip` 을
`source_video_id` 별로 쪼개지 않고 전체 분모로만 읽는다(`harness-v1-design.md` §4-1).
negative 클립이 0이면 값은 0이 아니라 `null` + `NO_NEGATIVE_CLIPS` 다.

### 2-4. `recall_macro` / `precision_macro` — macro 평균

**차용.** Sokolova & Lapalme, *A systematic analysis of performance measures for classification tasks*
(Information Processing & Management 45(4):427–437, 2009). macro 평균은 클래스를 동등하게 대하고,
micro 평균은 큰 클래스에 끌려간다는 그 구분이 근거다.

**왜 macro 인가.** A tier 시퀀스가 SIGNAL 2,065 : 안전모 412 로 5배 차이 난다. micro 로 재면
신호위반만 잘하는 모델이 전체 점수를 가져간다. 제품은 4종을 **모두** 약속했으므로 클래스를
동등하게 보는 macro 가 맞다. 구현은 값이 `null` 인 클래스(분모 0)를 평균에서 빼는 방식이라,
**데이터가 없는 클래스가 0점으로 평균을 끌어내리지 않는다** — 5절의 null 규율과 같은 원칙.

### 2-5. 5×5 confusion — 4종 + `NONE`

**차용.** 특정 논문이 아니라 검출 평가 일반의 관례 — 정답 클래스 외에 background/negative 클래스를
행·열로 두어 「아무것도 아닌 것을 무엇으로 잘못 불렀나」를 보이게 하는 방식.

**왜.** 오분류의 **방향**이 제품 비용과 직결된다. 「중앙선침범을 진로변경위반으로 불렀다」는
신고 유형이 틀리는 것이고, 「정상을 신호위반으로 불렀다」는 사용자를 헛걸음시키는 것이다.
단일 accuracy 는 둘을 같은 실점으로 뭉갠다.

**채워졌다 (F12 해소, 2026-09-16).** `NONE` 은 B tier 의 검토 완료 negative 클립에서 온다.
두 tier 를 잇는 `manifests/ab_mixed`(A 120 + NONE 30)가 생겨 5×5 가 실제로 5×5 다.
A tier 단독(`a_aihub`)으로 채점하면 여전히 `NONE` 행·열이 0이다 — manifest 선택이 곧 측정 범위다.

### 2-6. `target_correctness` — bbox IoU ≥ 0.5

**차용.** Everingham 등, *The PASCAL Visual Object Classes (VOC) Challenge*(IJCV 88(2):303–338, 2010)의
overlap criterion — 예측 bbox 와 정답 bbox 의 IoU ≥ 0.5 면 맞은 것으로 센다. **임계값 0.5까지
그대로 가져왔다.**
이 논문에는 클래스 평균(mAP) 열이 없고 클래스별 AP만 있다(VOC2007 최고 AP 9.4–43.2%, `metric-benchmark-scores.md` §2) — 「VOC mAP」를 이 논문 인용으로 적지 않는다.

**왜 이 전통인가.** 우리 제품에서 「대상 차량을 옳게 짚었는가」는 신고 자료의 근간이다(엉뚱한 차를
신고하면 자료 전체가 무의미하다). 픽셀 완전일치를 요구하면 실제 탐지기는 전부 0점을 받으므로,
오래 검증된 느슨한 임계값 관례를 따르는 것이 합리적이다.

**주의 — 우연히 같은 값 (F8).** `classification._TARGET_BBOX_IOU_THRESHOLD`(2-D 공간 IoU)와
과거 `candidate` 의 시간 IoU 임계값이 둘 다 0.5였지만 **서로 무관한 값**이다. 전자만 VOC 근거가 있다.

### 2-7. `exact_accuracy` — 번호판 전체 일치

**차용.** Laroca, Zanlorensi, Gonçalves, Todt, Schwartz, Menotti,
*An Efficient and Layout-Independent Automatic License Plate Recognition System Based on the YOLO Detector*
(IET Intelligent Transport Systems 15(4):483–503, 2021)의 **end-to-end recognition rate** —
번호판 단위로 세며 부분 일치를 인정하지 않는다.

**왜 문자 단위가 아니라 판 단위인가.** 신고에 쓰이는 값은 번호판 **전체**다. 7자 중 6자를 맞힌
결과는 신고서에서 0점짜리다. CER 이 낮아도 제품 가치는 0일 수 있으므로, 대표 지표는 전체 일치여야
하고 CER 은 **진단용**으로만 둔다(§9-3 「Detection/Association/CER 등 diagnostics」).

**CER 의 출처.** ICDAR Robust Reading 계열의 normalized edit distance(Levenshtein 기반).
아직 구현하지 않았다.

**지금 잴 수 없다.** A tier 는 번호판이 비식별 처리되어 문자 정답이 없다. C tier 확보(F1) 전까지
`null` + `NO_PLATE_GT` 다(`harness-v1-design.md` §4-3).

### 2-8. `wrong_accept_rate` — 확신에 차서 틀리게 읽기

**요약식.** 분모는 **정답이 `UNREADABLE` 인 항목 수**. 분자는 그 중 기권하지 않고 값을 낸 건수.

**차용(느슨).** 생체인식의 False Accept Rate — ISO/IEC 19795-1 이 「비진짜 시도가 잘못 수용된 비율」로
정의한 것. **비유만 가져왔고 식은 다르다.**

**왜 이 형태인가 — 이 지표의 핵심.** 판독 불가능한 번호판에 확신을 담아 값을 내는 것은
「틀린 글자를 읽었다」와 다른 **종류**의 실패다. 사용자는 검증할 방법이 없는 값을 신고서에 옮긴다.
그래서 분모를 「기권하지 않은 예측」이 아니라 **「애초에 읽을 수 없었던 항목」**으로 잡아야
지표가 그 실패만 본다. v1 구현은 이 분모를 틀리게 잡아(abstain 항목을 분모에서 빠뜨려)
판독 불가 번호판에 대한 오탐을 항상 0으로 보고했고, 검증할 GT 가 없어 그 사실이 드러나지 않았다.
그래서 해당 분기를 비활성화가 아니라 **삭제**했다(`harness-v1-design.md` §9 F6).

**문헌 대응이 왜 느슨한가.** 생체인식의 FAR 은 「가짜를 진짜로 받아들임」으로 분모가 impostor 시도다.
우리는 「읽을 수 없는 것을 읽었다고 주장함」이라 분모가 입력의 성질(legibility)이다.
같은 걱정을 다루지만 같은 식이 아니다. 인용할 때 이 차이를 지워서는 안 된다.

### 2-9. `abstention_recall` — 기권해야 할 때 기권했나

**요약식.** 정답이 `UNREADABLE` 인 항목 중 예측이 `abstained=true` 인 비율.
`wrong_accept_rate` 와 **분모가 같고 합이 1** 이다 — 같은 교차표의 두 칸이다.

**차용(느슨).** reject option / selective classification 계보 —
C. K. Chow, *On optimum recognition error and reject tradeoff*(IEEE Trans. Information Theory 16(1):41–46, 1970)이
error–reject tradeoff 를 세웠고, El-Yaniv & Wiener(2010)가 risk–coverage 로 형식화,
Geifman & El-Yaniv, *Selective Classification for Deep Neural Networks*(NeurIPS 2017)가 DNN 으로 확장했다.

**왜 이 전통인가.** 제품 약속이 「모르면 `확인 필요`로 둔다」(초기 테스트 케이스 7·12번)이므로,
**기권 자체가 정답인 상황**이 존재한다. 기권을 실패로 세는 지표 체계로는 이 약속을 측정할 수 없다.

**문헌과 다른 점.** 문헌은 risk–coverage **곡선**(기권률을 움직이며 위험을 본다)을 본다.
우리는 곡선이 아니라 **고정된 한 점**의 recall 을 낸다. 임계값 sweep 이 없기 때문이며,
그래서 「기권을 늘려 wrong-accept 를 줄였다」와 「판독이 좋아졌다」를 지금 구분하지 못한다.
C tier 확보 후 risk–coverage 곡선으로 확장할 여지가 있다.

### 2-10. Hard-negative FPR (미구현, F4)

**차용(느슨).** Shrivastava, Gupta, Girshick, *Training Region-based Object Detectors with
Online Hard Example Mining*(CVPR 2016) 계열의 hard negative 개념 — 쉬운 음성이 압도적으로 많고
어려운 음성이 소수라는 관찰.

**차이.** 문헌은 이것을 **학습 기법**으로 쓴다. 우리는 **평가 분할**로 쓴다 — 실선 침범 ↔ 점선
정상 변경처럼 사람도 헷갈리는 대조쌍을 따로 모아 그 위에서만 FPR 을 낸다.
전체 FPR 은 쉬운 음성에 희석되어 이 모델의 실제 위험을 감춘다.

### 2-11. `cost_per_case` / `cost_per_source_video_hour` — 문헌 없음

출처가 되는 논문이 없다. 원가 구성식(`initial-evaluation-plan.md` §2 각주)은 이 제품의 파이프라인에서
직접 나온 것이다. 문헌에서 온 것이 아니라 **회계에서 온 것**이므로, 인용하지 않는다.

다만 v4 §9-3 이 강제하는 「runtime economics 와 eval execution cost 를 섞지 않는다」는
측정 위생 원칙이고, 이는 벤치마크 비용 보고 일반의 상식과 같은 방향이다.

---

## 3. 문헌에 없는 것 — 우리가 만든 것

「논문에서 차용했다」고 말하면 **안 되는** 항목들이다.

| 항목 | 무엇 | 왜 만들었나 |
| --- | --- | --- |
| `containment_rate` | coarse 창이 정답 onset 을 품은 비율 | tIoU 를 버리면서 창의 품질을 볼 보조 신호가 필요했다. 매칭 조건이 아니다 |
| `onset_error_sec` 의 표본 규칙 | 적중한 사건만 표본에 넣는다 | 매칭되지 않은 예측의 오차는 무엇과 비교할지 정의되지 않는다 |
| `tolerance_sec = 2.0` | 허용오차 값 | 근거 없는 잠정값. 라벨 폭 편차를 재서 정해야 한다(F8) |
| `wrong_accept_rate` 의 분모 | 「정답이 UNREADABLE 인 항목」 | 2-8 참조. FAR 의 분모와 다르다 |
| `scoring: INCLUDED / EXCLUDED / BOUNDARY_EXCLUDED` | 채점 대상 분류 | 클립 경계에 걸친 사건을 조용히 빼면 분모가 줄어 recall 이 부풀려진다 |
| `coverage` 사유 문자열 | 무엇을 왜 못 냈나 | 5절 |
| 순환 경고(`CIRCULARITY`) | mock 유래 GT 로 낸 점수임을 결과가 스스로 말한다 | 5절 |
| `cost_per_case` 집계 키 | `run_ref` 가 아니라 `case_id` | run 이 산출되지 않은 attempt 가 통째로 빠져 비용이 과소 보고된다 |

---

## 4. 문헌을 따르지 않기로 한 것

| 문헌 관행 | 우리 선택 | 근거 |
| --- | --- | --- |
| 시간 IoU 로 후보 매칭 (TALL 등) | onset 지점 오차 | `span` 이 「정답 주장」이 아니라 「더 볼 창」이다(계약 v1.1 §4-1) |
| onset collar 250 ms (DCASE 2016 공식 채점) | ±2.0 s | 사람 초 단위 판독 + 창의 대표값. **잠정** |
| FP/hour | FP/clip | B tier 에 시간 분모가 설 negative 가 부족하다(§4-1) |
| micro 평균 | macro 평균 | 유형 불균형 5배. 제품은 4종을 모두 약속했다 |
| 부분 문자 점수(CER)를 대표 지표로 | 전체 일치를 대표, CER 은 진단 | 신고서에 부분 일치는 0점이다 |
| risk–coverage 곡선 | 고정 임계값 한 점 | 임계값 sweep 이 아직 없다. 확장 여지 |
| 데이터 없으면 0점 | `null` + 사유 | 5절 |

---

## 5. 지표가 아니라 **측정 위생**에서 빌려온 것

지표 자체는 아니지만 하니스 설계를 지탱하는 규범이다.

- **데이터가 없는 지표는 0이 아니라 `null` + 사유.** 0으로 적으면 「측정했고 나빴다」로 오독된다.
  「측정 못 했다」와 「측정했고 나빴다」를 구분해 적는 태도는 데이터셋·모델 문서화 규범
  (Gebru 등 *Datasheets for Datasets*, CACM 64(12), 2021 / Mitchell 등 *Model Cards for Model Reporting*, FAT\* 2019)이
  요구하는 것과 같은 방향이다. **직접 차용은 아니다.**
- **runner / scorer 분리와 immutable prediction**(v4 §9-2). 예측을 한 번 고정해 두고 정답지·지표
  정의를 바꿔 가며 재채점하는 구조는 TREC 이래 벤치마크 평가의 표준 형태(run 제출과 judgment 분리)와 같다.
  우리 근거는 그보다 실무적이다 — 지표를 고칠 때마다 유료 API 를 다시 부르지 않기 위해서다.
- **순환 경고.** mock tier 의 onset·true_text 는 채점 대상 예측과 같은 fixture 에서 유도한 값이라
  점수가 구조상 만점이다. 이 사실을 결과 파일이 스스로 말하게 했다(`candidate.CIRCULARITY`,
  `plate.CIRCULARITY`). 문헌 출처는 없고, **가짜 성능 주장을 막기 위한 자체 규율**이다.
- **분자 0 경고.** wrong-accept 사례가 0건인 것은 「안전하다」가 아니라 「그런 케이스가 pack 에 없다」다
  (`plate.ZERO_NUMERATOR`).

---

## 6. 이 문서를 인용할 때

- 「Recall@K · onset tolerance · FP rate · macro 평균 · IoU 0.5 · 전체 일치 인식률」까지는
  **문헌 관행을 따랐다**고 말해도 된다.
- 「wrong accept rate · abstention recall」은 **개념을 빌렸으나 식은 우리 것**이라고 말해야 한다.
- 「containment_rate · tolerance 2초 · cost 지표」는 **우리가 정했다**고 말해야 한다.
- 어느 경우에도 지금 실측값을 성능 근거로 말할 수 없다 — mock tier 는 순환이고, plate 는 GT 가 없고,
  `NONE` 행·열은 비어 있다.

---

## 참고문헌

1. J. Gao, C. Sun, Z. Yang, R. Nevatia. **TALL: Temporal Activity Localization via Language Query.** ICCV 2017. arXiv:1705.02101.
2. A. Mesaros, T. Heittola, T. Virtanen. **Metrics for Polyphonic Sound Event Detection.** Applied Sciences 6(6):162, 2016. doi:10.3390/app6060162. (DCASE event-based metrics: <https://dcase.community/challenge2016/metrics>)
3. NIST. **TRECVID Surveillance Event Detection Evaluation Track** — NDCR = P_Miss + β·R_FA. <https://www.nist.gov/itl/iad/mig/trecvid-surveillance-event-detection-evaluation-track>
4. M. Sokolova, G. Lapalme. **A systematic analysis of performance measures for classification tasks.** Information Processing & Management 45(4):427–437, 2009.
5. M. Everingham, L. Van Gool, C. K. I. Williams, J. Winn, A. Zisserman. **The PASCAL Visual Object Classes (VOC) Challenge.** IJCV 88(2):303–338, 2010.
6. R. Laroca, L. A. Zanlorensi, G. R. Gonçalves, E. Todt, W. R. Schwartz, D. Menotti. **An Efficient and Layout-Independent Automatic License Plate Recognition System Based on the YOLO Detector.** IET Intelligent Transport Systems 15(4):483–503, 2021. arXiv:1909.01754.
7. ISO/IEC 19795-1, **Information technology — Biometric performance testing and reporting — Part 1: Principles and framework.**
8. C. K. Chow. **On optimum recognition error and reject tradeoff.** IEEE Transactions on Information Theory 16(1):41–46, 1970.
9. Y. Geifman, R. El-Yaniv. **Selective Classification for Deep Neural Networks.** NeurIPS 2017.
10. A. Shrivastava, A. Gupta, R. Girshick. **Training Region-based Object Detectors with Online Hard Example Mining.** CVPR 2016, pp. 761–769.
11. T. Gebru et al. **Datasheets for Datasets.** Communications of the ACM 64(12):86–92, 2021.
12. M. Mitchell et al. **Model Cards for Model Reporting.** FAT\* 2019.
13. ICDAR Robust Reading Competition — normalized edit distance(1−N.E.D) 랭킹 지표. <https://rrc.cvc.uab.es/>

---

## 참조

`architecture/module-architecture.md` §9-3 · §9-4 ·
`modules/eval/initial-evaluation-plan.md` §2 · §3 ·
`modules/eval/harness-v1-design.md` §4-1 · §4-3 · §5 · §9(F1 · F4 · F6 · F7 · F8 · F12) ·
`eval/scorers/candidate.py` · `classification.py` · `plate.py` · `cost.py`
