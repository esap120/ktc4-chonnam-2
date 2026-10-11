# 오래 걸리는 AI 작업의 사용자 흐름 · 다시 받기 · 진행 표시 조사

조사일 2026-10-01 · 작성 신유민 · **조사이고 결정이 아니다.**

계기: PR #146 멘토 리뷰 — ① 백엔드 변경을 웹에 실시간으로 반영하는 기법 학습, ② 후보 비교 UI는 Apple 기기 비교·OpenAI 모델 비교 참고(3개 고정), ③ rank 1은 자동으로 뒤 동선까지, 나머지는 선택 시 이어지게.

표기: 【추측】은 출처로 확인하지 못한 판단, (2차)는 원문 대신 2차 출처만 본 것.

## 1. 비슷한 제품의 흐름

| 제품 | 시작 전 | 진행 중 | 결과에서 고치는 곳 |
| --- | --- | --- | --- |
| ChatGPT Deep Research | **명확화 질문**으로 되묻는다 | 단계와 읽은 출처를 보여 줌, 자리를 떠도 완료 알림 | 시작 전 답변 ([FAQ](https://help.openai.com/en/articles/10500283-deep-research-faq)) |
| Gemini Deep Research | **연구 계획**을 먼저 보여 줌 | — | 시작 전 「Edit plan」 ([도움말](https://support.google.com/gemini/answer/15719111?hl=en)) |
| ChatGPT agent | 작업 지시 | 브라우저 조작을 실시간으로 보여 줌 | 중간 개입·「Take over」·중요 행동 전 확인 ([OpenAI](https://openai.com/index/introducing-chatgpt-agent/)) |
| Codex cloud | 최대 4개 시도 동시 실행 | 백그라운드 | 시도 중 하나를 골라 PR (2차, [agent37](https://www.agent37.com/blog/codex-cloud)) |
| **Opus Clip** (가장 비슷) | 장면 프롬프트 + **처리 구간 슬라이더** | 대기 | 점수순 클립 여러 개, 구간·키워드 바꿔 재실행 ([구간 지정](https://help.opus.pro/docs/article/select-timeframe)) |
| Twelve Labs Playground | 자연어 검색어 | — | 관련도순 클립 + 구간 시각 + 「See Full Video」 ([문서](https://docs.twelvelabs.io/docs/resources/playground/search)) |
| 삼쩜삼 | 연동 인증 | — | 예상 환급액 → 신고 결정. 「환급액 도착」 과장 문구로 공정위 제재 ([뉴스](https://v.daum.net/v/20251228120227036)) |

공통점: **시작 전 범위 확정 · 진행 중 단계 표시 · 끝나면 알림.** 영상 장면 찾기 제품은 「순위 매긴 후보 + 각 후보 구간 + 원본으로 가는 길」을 쓴다. 결과를 과장하는 문구는 규제 위험이 있다.

## 2. 원하는 결과가 아닐 때 다시 받는 방법

| 패턴 | 쓰는 곳 | 장점 | 단점 |
| --- | --- | --- | --- |
| 다른 후보 보기 | Opus Clip, Codex, Sora | 재실행 없이 즉시 | 후보가 많으면 비교 피로 |
| 범위 좁히기·넓히기(시간 구간) | Opus Clip | 빠르고 정확도 오름 | 사용자가 대략의 시각을 알아야 함 |
| 입력 고쳐 재실행 | Opus Clip, Twelve Labs | 원인이 입력이면 효과 큼 | 다시 기다림 |
| 직접 지정(타임라인) | Opus·Descript 편집기 | 항상 성공하는 최후 수단 | 손이 많이 감, 구현 비용 큼 |
| 명확화 질문(시작 전) | ChatGPT DR, Gemini | 헛도는 실행 방지 | 시작이 늦어짐 |
| 같은 입력으로 재생성 | Perplexity, Sora | 버튼 하나 | 탐지 작업은 같은 결과가 나오기 쉬움 【추측】 |
| 「아니에요」+이유 | Google Photos Ask Photos ([도움말](https://support.google.com/photos/answer/15318661)) | 평가 데이터가 쌓임 | 그 자리에서 결과는 안 바뀜 |

대신고에 맞는 순서 【추측】: **① rank 2·3 후보 보기 → ② 시간 구간 지정 후 재탐색 → ③ 상황 설명 고쳐 재실행 → ④ 타임라인에서 직접 지정.** 각 단계에서 「이게 아니에요」 이유를 로그로 남긴다. 명확화 질문은 대화로 따로 두지 않고 업로드 화면 입력칸(시각·차량)으로 흡수한다.

현재 문서와의 대응: ①은 결과 화면 「다른 후보 보기」(core-user-flow, #173), ②·③은 결과 없음 화면의 「넓히기」·「기억 단서 고치기」(와이어프레임 12), 후보를 고른 뒤 다시 준비하는 경로는 #106에서 계약 대기.

## 3. 진행 상태를 실시간으로 보여주는 기법

| 기법 | 원리 | 장점 | 부담 |
| --- | --- | --- | --- |
| Short polling | N초마다 `GET` | 일반 HTTP, 프록시 설정 0, 서버는 저장소를 읽기만 | 최대 N초 지연, 요청 낭비 |
| Long polling | 변화가 생길 때까지 응답 보류 | 지연 짧음 | 타임아웃·재요청 처리 ([RFC 6202](https://datatracker.ietf.org/doc/html/rfc6202)) |
| SSE | 응답 하나를 열어 두고 서버가 단방향 이벤트 전송, 자동 재연결 | 브라우저 `EventSource` 기본 지원, FastAPI 지원 ([FastAPI](https://fastapi.tiangolo.com/tutorial/server-sent-events/)) | HTTP/1.1 도메인당 연결 6개 ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)), nginx `proxy_buffering off`·긴 read timeout |
| WebSocket | 양방향 연결 ([RFC 6455](https://datatracker.ietf.org/doc/html/rfc6455)) | 양방향, 저지연 | Upgrade 헤더·60초 유휴 끊김·ping·재연결 직접 구현 ([nginx](https://nginx.org/en/docs/http/websocket.html)) |
| HTTP/2 Server Push | — | — | Chrome에서 제거, 쓰지 않음 |

참고: OpenAI API 스트리밍은 SSE를 쓴다고 문서에 적혀 있다 ([OpenAI](https://developers.openai.com/api/docs/guides/streaming-responses)).

대신고 판단 근거: 작업이 수십 초~수 분이고 단계가 8개뿐이라 2~3초 지연은 체감되지 않는다. API가 job 상태를 저장소에서 읽기만 하면 돼서 워커와 웹 연결이 섞이지 않는다. → **short polling으로 시작하고, 같은 상태 API 옆에 SSE를 나중에 덧붙일 수 있다.** 양방향이 필요 없어 WebSocket은 이득이 없다. `module-architecture.md` 부록의 「Progress: polling 우선」과 같은 방향이다.

진행 표시 UX: 10초 넘는 작업에는 진행 표시를 쓴다([NN/g](https://www.nngroup.com/articles/progress-indicators/)). 퍼센트·ETA는 정확히 낼 수 없으므로 **단계 체크리스트**가 정직하다. 탭을 떠나도 되게 case/job id를 URL에 넣어 새로고침해도 이어지게 한다.

## 4. 후보 비교 UI (멘토 참고 사이트)

| | [Apple iPhone 비교](https://www.apple.com/iphone/compare/) | [OpenAI 모델 비교](https://developers.openai.com/api/docs/models/compare) |
| --- | --- | --- |
| 열 | 최대 3개, 열마다 드롭다운으로 교체 | 3개 나란히 (열 교체 방식은 확인 필요) |
| 행 | 카테고리별 묶음(디스플레이·칩·카메라…) | 성능·가격·컨텍스트·지식 컷오프·지원 기능 |
| 강조 | 같은 행에 값을 나란히 | 열 머리에 한 줄 요약 + 수치 |

옮길 점: 열 3개 고정(rank 1~3), 열 머리에 썸네일·구간·한 줄 요약, **행은 신고자료 필드와 같게**(시각·번호판·차량·위반 근거), 열마다 「이 후보로 준비」 하나. 와이어프레임 09(둘만 견주기)의 「같은 행에 맞춰 놓기」와 같은 원리다.
