# search/experiments

재현 가능한 실험 기록을 둔다. 입력/설정/결과/실패/다음 learning을 남긴다. AI 원문과 원본 영상은 저장소에 두지 않는다. 신규 실험 결과 원본(JSON·JSONL)은 로컬에만 보관하고, Git에는 설정·수치 요약·해석을 담은 Markdown 보고서를 남긴다.

- [coarse-fine-probe-summary-2026-09-12.md](coarse-fine-probe-summary-2026-09-12.md) — 약 39분 주행 영상 Coarse·Fine 탐침 총정리
- [decision-trace-guide.md](decision-trace-guide.md) — 로컬 진단 실행과 전체 관찰 출력 형식
- [7영상 진단 실행 결과 JSON](decision-trace-seven-video-2026-09-26-results.json) — p3·진단 형식 각 1회의 수치·상태·해시
- [프록시 경유 영상 샘플링](gemini-proxy-video-sampling-2026-09-28.md) — 로컬 fps·해상도와 관계없이 1 fps·low로 처리되고 파라미터로 바꿀 수 없음 ([JSON](gemini-proxy-video-sampling-2026-09-28-results.json))
- [이미지 프레임 probe](gemini-image-frame-probe-2026-09-28.md) — image_url은 수용되고 프레임당 1,100토큰(해상도 무관)·fps 제어 가능하나 해상도 노브는 없음 ([JSON](gemini-image-frame-probe-2026-09-28-results.json))
- [Fine 이미지 정확도](gemini-fine-image-accuracy-2026-09-28.md) — 정답 구간을 줘도 fps 1/2/4로 실선 판별 정확도가 오르지 않음 ([JSON](gemini-fine-image-accuracy-2026-09-28-results.json))
- [Coarse→Fine 이미지 트레이스](gemini-coarse-fine-image-trace-2026-09-28.md) — 실제 구조를 이미지(coarse 2fps/fine 4fps)로; 검출 2→4, 비용 약 30배, 141927 여전히 놓침 ([JSON](gemini-coarse-fine-image-trace-2026-09-28-results.json))
- [느린 영상 토큰 probe](gemini-video-slowdown-token-probe-2026-09-29.md) — 영상을 늘리면 토큰 = 재생 길이 × 66, 0.5x·0.25x로 원본 2·4 fps를 영상 단가로 넣음 ([JSON](gemini-video-slowdown-token-probe-2026-09-29-results.json))
- [Coarse→Fine 느린 영상 트레이스](gemini-coarse-fine-slowdown-trace-2026-09-29.md) — 이미지와 같은 프레임 밀도(coarse 0.5x/fine 0.25x)를 영상으로; 위반 2/4·2/4, 토큰은 이미지의 약 1/15 ([JSON](gemini-coarse-fine-slowdown-trace-2026-09-29-results.json))
- [Coarse→Fine handoff 트레이스](gemini-handoff-trace-2026-09-29.md) — diagnostic-v1 대조로 handoff를 이미지·느린 영상(coarse 2/fine 4 fps) 각 2회; 효과 구분 안 됨, 음성 끌림 0, p3 대비 개선 없음 ([이미지 JSON](gemini-handoff-image-trace-2026-09-29-results.json) · [느린 영상 JSON](gemini-handoff-slowdown-trace-2026-09-29-results.json))
- [Fine 고정 구간·불확실성 규칙](gemini-fine-window-uncertain-2026-10-01.md) — 정답 구간을 Fine에 직접 줘 diagnostic-v1 대 uncertain-v1 각 3회; 판정 차이 0, YT_0003은 대상을 맞게 잡고도 원거리 횡이동을 못 봄, 141927은 가까운 다른 SUV를 대상으로 잡음 ([JSON](gemini-fine-window-uncertain-2026-10-01-results.json))
- [Fine crop × 대상 힌트](gemini-fine-crop-hint-2026-10-01.md) — 원본 해상도 crop·target_hint 각각·함께 3회; 대상 연결은 고쳐지나 위반 2구간 검출 0/24, 점선 오탐 0; 141927을 4–10초로 넓혀도, 느린 영상+crop으로 보내도 0/3 ([JSON](gemini-fine-crop-hint-2026-10-01-results.json))
- [Coarse recall 프롬프트 변형](gemini-coarse-recall-prompt-2026-10-01.md) — Coarse만 느린 영상으로 p3·subject-v1·multi-v1 각 3회; recall 6/12로 동일, 141927은 위반 SUV를 찾지만 시각이 늦음 ([JSON](gemini-coarse-recall-prompt-2026-10-01-results.json))
- [느린 영상 시각 환산 검증](gemini-slow-video-time-probe-2026-10-01.md) — 프레임 대응(API 없음)과 빨간 사각형 probe; 변환·모델 응답 모두 0.5초 이내, Coarse 시각 오차는 환산 문제가 아님 ([JSON](gemini-slow-video-time-probe-2026-10-01-results.json))
- [프록시 인라인 요청 크기 한도](gemini-proxy-size-probe-2026-10-01.md) — 10초 영상을 10–61 MiB로 키워 1회씩; 요청 81 MiB까지 성공, 토큰 불변·응답 시간만 증가 ([JSON](gemini-proxy-size-probe-2026-10-01-results.json))
- [운영 경로 검증 v3](search-v3-production-verify-2026-10-01.md) — GeminiProvider 그대로 7클립 3회; 위반 2/4·1/4·1/4, 오탐 0, 회차 평균 5.5만 토큰, 영상 밖 후보 1건(#181) ([JSON](search-v3-production-verify-2026-10-01-results.json))
- [Coarse 원본 4 fps](gemini-coarse-4fps-2026-10-02.md) — Coarse p3를 0.25x로 3회; 적중 6→9/12지만 141927 증가분은 틀린 차량(흰색 SUV) 구간이 정답과 겹친 것, YT_0003 변화 없음, 토큰 1.85배 ([JSON](gemini-coarse-4fps-2026-10-02-results.json))
- [운영 경로 모델 비교 3.1-pro](search-v3-pro-model-verify-2026-10-02.md) — v3 구조 그대로 모델만 gemini-3.1-pro-preview로 3회; 위반 3/4·2/4·3/4지만 위반 없음 정답 9/9→2/9(점선 정상 변경도 실선으로), 141927 HIT는 틀린 차량. high는 위반 없음 0/9 ([JSON](search-v3-pro-model-verify-2026-10-02-results.json), [high JSON](search-v3-pro-model-high-2026-10-02-results.json))
- [운영 구조 모델 비교 gpt-5.6-luna](search-v3-gpt-luna-image-2026-10-02.md) — 영상 미지원이라 이미지 전송(Coarse 2 / Fine 4 fps)으로 3회; 위반 2·1·2/4, 오탐 0, 141927·YT_0003은 Coarse 후보 0, 토큰 flash 영상의 약 2.5배 ([JSON](search-v3-gpt-luna-image-2026-10-02-results.json))
- [운영 구조 모델 비교 gpt-5.6-sol](search-v3-gpt-sol-image-2026-10-02.md) — 이미지 전송 3회; 위반 2/4 ×3, 오탐 0. 141927에서 처음으로 위반 SUV·정답 시각을 잡았으나 선을 점선으로 봐 기각 ([JSON](search-v3-gpt-sol-image-2026-10-02-results.json))
- [Fine 고정 구간 sol × AI-Hub 참고 예시](gpt-sol-fine-fewshot-2026-10-02.md) — 예시 3장 유무 각 24호출; 양성 10/12 같음·음성 11→12/12로 효과 구분 안 됨. 예시 없이도 sol은 720p 고정 구간에서 141927을 3/3(정답 차량·실선) ([JSON](gpt-sol-fine-fewshot-2026-10-02-results.json))
- [Fine 고정 구간 sol 해상도·detail·구간 폭](gpt-sol-fine-resolution-window-2026-10-02.md) — 하나씩 바꾼 4조건 각 24호출; 141927은 720p 9/9 대 360p 3/6로 해상도가 원인, detail·구간 폭은 무관. 720p 토큰 약 3배 ([JSON](gpt-sol-fine-resolution-window-2026-10-02-results.json))
- [sol 파이프라인 Fine 720p](search-v3-gpt-sol-fine720-2026-10-02.md) — Fine만 720p로 3회; 위반 3·3·2/4, 오탐 0, 141927 처음 통과(2/3). 남은 실패는 모두 Coarse 후보 없음. 토큰 360p의 1.7배 ([JSON](search-v3-gpt-sol-fine720-2026-10-02-results.json))
- [sol 파이프라인 Fine 720p · set1 10클립](search-v3-gpt-sol-fine720-set1-2026-10-04.md) — 10/02 최고 조건을 새 정답 10클립(사건 11)에 3회; 위반 1·1·1/11, Coarse가 정답 구간에 후보를 낸 건 33번 중 4번. 신호위반 Fine이 합법 출발을 `OBSERVED`로 오판(3건). 토큰 1.9배
- [Flash 운영 조건 set1 · 탐지 유형 1개 vs 4개](search-flash-set1-event-types-2026-10-09.md) — 스트리밍 A/B3회 완료(범위 오류 포함); A2·1·1/11 vs B0·0·0/11, Coarse14/33 vs7/33. 후보60→65·비용+7.4%, 이번 개발 표본에서 동시 입력 차이 관찰. 비교 비용₩1,433, 실패/probe 포함 확인 누적₩1,680(미확인 요청2개 별도).
- [AI Hub Coarse + sol Fine · 15개 영상](aihub-coarse-sol-fine-2026-10-04.md) — 정답 없이 1fps 탐지·IoU 추적으로 후보 63개 생성, Fine 720p 4fps 1회; 사건 구간 포함 7/13(앞뒤 4초 포함 10/13), 최종 정답 중첩 판정 2/13·신규 0/8·정상 3/3 기각. 대상 연결 오류·녹색 신호 오판 확인, 같은 set1 최종 1/11로 개선 없음
- [AI Hub LRCN 분류 + sol Fine · 15개 영상](aihub-lrcn-sol-fine-2026-10-04.md) — 분류 후보 51개·독립 3종 Fine 1회; 정답 구간·종류 중첩 4/13, 신규 1/8·정상 후보 오탐 0/3, 앞선 공간 후보 조합 2/13보다 증가·토큰 35.4% 감소. 조건 차이·1회 실험으로 우월성 미확정
- [AI Hub + sol 토큰 분석](aihub-sol-token-analysis-2026-10-04.md) — 기존 51/63호출 분석; 최신 약 127만 토큰의 이미지 비중 추정 93.3%, 중복 이미지 22.3%·여유 구간 57.3%·정상 후보 입력 29.6%. 새 API 호출 없이 계산
- [AI Hub + sol 새 실험 설계](aihub-sol-budgeted-design-2026-10-04.md) — 5초 본문·fps 비교 후 대표 차선 표시 × 프롬프트 2×2, 통과 조건 전체 재검증. 단계 예산·오탐·사건 유지 기준을 사전 정의, 아직 실행하지 않음
- [p4-retired-2026-09-25/conditions.md](p4-retired-2026-09-25/conditions.md) — 종료한 p4의 구현 계획, 두 회차 조건·보고서·결과, 원문 프롬프트 보존
