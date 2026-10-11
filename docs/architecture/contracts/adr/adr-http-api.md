# ADR — HTTP API Contract (web ↔ api)

**Status:** Accepted — web Consumer review · case · recording boundary review 반영 완료. 계약은 `contract-http-api.md` `http-api/v1` `Final — Accepted`다.

**Decider:** 김준영 (`api` composition root, HTTP API Contract Producer)
**Date:** 2026-10-04 (Draft `http-api/v0`) · 2026-10-05 (리뷰 반영 · Final `http-api/v1` 승격)
**Contract:** `../contract-http-api.md`
**상위 결정:** [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247) RD-05 H-1 ~ H-6 (ACCEPTED 2026-10-04) · 입력 [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245) D-2 · D-3 · C-1 · C-3 · [#246](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/246) S-2 · S-4 · S-5
**Review:** [PR #265](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265) — [종합 결론](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#issuecomment-5994678000)(김준영, 2026-10-05)

---

## 1. Context

#247은 HTTP 경계의 Owner · endpoint 집합 · 202/200 기준 · polling 정지 조건 · upload 방식 · 오류 status 표를 정했고, 계약 문서 작성은 다음 단계로 넘겼다(Runtime Tech Spec §13). web은 아직 fixture 기반이라 실연동 전에 경로 · body · status를 하나로 고정해야 했다. #247 H-1은 계약을 Draft로 두고 web 확인 뒤 Final로 올리도록 정했고, 계약 §10이 web Consumer review와 case · recording boundary review를 승격 조건으로 적었다.

## 2. Decision

**#247에서 정한 것은 그대로 옮기고, HTTP에만 있는 의미만 새로 정했다.** 계약 스키마는 계약 문서에만 둔다.

#247에서 그대로 온 것 — endpoint 8개 · job 상태 endpoint 없음 · domain action = command `kind` · JobRecord ≥ 1 발주면 `202`, 아니면 `200`(composition root가 append 목록으로 판단) · body = case-command 응답 그대로 · `running_jobs=[]`이면 polling 정지 · 1 request = 1 file · 응답 전 publish · 등록 완료 · H-6 status 표.

Draft(`http-api/v0`)에서 새로 정한 것:

- **오류 envelope = case-command 응답 모양.** case 실패와 transport 실패를 web이 같은 코드로 읽는다. case 실패는 case body 그대로, transport 실패는 `http.*` code와 `case_view=null`.
- **HTTP 층은 command body 모양을 검사하지 않는다.** case가 이미 모양 오류를 `invalid_payload`로 판정하므로(`src/daesingo/case/command.py`) 두 층이 같은 판단을 나눠 하지 않게 했다. 예외는 path와 body의 `case_id` 불일치 하나(transport 불일치).
- **422 = transport는 정상, 내용을 domain · capability가 거부.** 400 = transport 단계에서 읽을 수 없음. 415 = request `Content-Type`. 그래서 「등록할 수 없는 영상」은 415가 아니라 422(`http.source_rejected`)다.
- **resource isolation.** 다른 case의 ref는 존재 여부와 무관하게 `404 http.not_found`. 소유는 recording의 case↔asset 연결로 판단한다.
- **소유했지만 bytes가 없으면 `404 http.ref_unavailable`.**
- **asset 「생성 전」 응답을 두지 않는다.** ReportPackage는 신고용 영상이 있어야만 존재하므로(ReportPackage 계약 §8.1) `artifact_ref`가 보이는 시점에는 이미 생성돼 있다.
- **upload `filename`은 사용자 원본 파일명으로 recording에 넘긴다.** recording은 파일명에서 시각 출처(`FILENAME`)를 찾는다.

리뷰에서 정해 `http-api/v1`에 넣은 것(PR #265):

- **원본은 `INTAKE`에서만 추가한다 → 그 밖에는 `409 http.source_not_allowed`.** 거부 규칙은 case 결정이다(product에 분석 시작 뒤 upload 흐름이 없고 `START_ANALYSIS` 초안이 `INTAKE` 전용). 같은 파일이 `INTAKE`에서는 받아지므로 내용 거부(422)가 아니라 상태 충돌(409)이고, HTTP 층이 만드는 오류라 `case_view=null`이다.
- **upload 실패는 recording이 돌려준 실패 종류로만 나눈다.** 결정적 거부(영상이 아님 · 지원하지 않는 구조, `UNSUPPORTED_MEDIA`) → `422 http.source_rejected`, 일시 장애(저장소 · ffprobe 등 도구 · recording dependency, `TEMPORARY_FAILURE`) → `503 http.dependency_unavailable`. HTTP 층은 메시지나 파일 내용으로 추론하지 않는다 — recording 제안 그대로. ffprobe 실패의 세부 분류는 recording 구현 후속이다.
- **`http.*`의 `message_key` = `error.code`.** 화면 문구는 web이 code별로 매핑한다(web 제안). `case.command.*`의 키는 case-command가 정한다.
- **upload 응답 유실은 `manifest_summary.file_count`로 확인한다.** 순차 upload 전제로, 보내기 전 `N`이면 `N + 1` → 이미 반영(다시 보내지 않음), `N` → 다시 보냄. case가 연결마다 `file_count` +1(같은 transaction)이고 `case_rev`는 올리지 않는다고 답했다(#270).
- **web은 `failed_file_count`를 화면 판단에 쓰지 않는다.** 실패 파일은 web이 요청 파일명과 실패 응답을 짝지어 표시하고, 새로고침 뒤 복원은 MVP 범위 밖이다(web 확인).
- **빈 case 예시 = case 결정 값.** `case_` + uuid4 hex · `case_rev=1` · `INTAKE` · hints 네 키 `null` · manifest 0 / `range:null` · `progress` 8단계 전부 `PENDING`(#270).
- **§5.5 FrameRef 배치 승인.** composition root가 소유를 확인한 뒤 recording `read_frame`을 부른다 — case가 bytes를 중계하지 않는다(recording 승인).

## 3. 기각한 안

- **`410 Gone`(asset 정리 뒤)** — `availability=UNAVAILABLE`은 「존재하지 않음」과 「접근 · decode 불가」를 함께 뜻해 영구성을 말할 근거가 없다. RFC 9110은 영구성을 모르면 404를 쓰라고 한다. purge 뒤 ref 의미(RD-10)가 정해지면 다시 본다.
- **asset 생성 전 `409`** — 생성 전에는 web이 가진 ref가 없으므로 쓰일 경로가 없다.
- **FrameRef 실패를 `500`** — S-4 보장 위반 가능성이 있지만 web에게는 재시도 대상이 아니다. 일시 실패만 `503`.
- **FastAPI 기본 422 `{"detail": ...}`** — envelope이 둘이 되고 case `invalid_payload`와 겹친다.
- **upload part 형식 · 확장자로 영상 판정** — client가 보낸 값이라 믿을 수 없고, 판정은 recording 등록의 일이다.
- **손상 영상을 모두 `201 + availability=UNAVAILABLE`로 등록(case 제안, 리뷰 중 철회)** — ffprobe가 실패하면 MediaStream을 식별할 수 없고, `media_stream_refs=[]` 허용 조건이 SourceAsset 계약에서 아직 Pending이다. `UNAVAILABLE`은 「유효한 ref의 대상이 있었지만 지금 쓸 수 없음」이라 등록 단계 거부와 의미가 섞인다(recording). web이 `failed_file_count`를 쓰지 않으므로 MVP에 막히는 것도 없다.
- **HTTP 층이 등록 실패를 메시지 · 도구 출력으로 422/503 추론** — recording taxonomy가 부족한 것을 transport가 메우면 두 층이 같은 판단을 나눠 갖는다. 보완 전에는 손상 파일도 `503`으로 나가는 것을 받아들였다.
- **upload 반영 확인을 `case_rev`로** — upload는 `case_rev`를 올리지 않는다(동시 upload 응답이 섞여도 분석 시작이 `stale_revision`에 걸리지 않게 하려는 case 결정).
- **이번 버전에 upload idempotency key · 시도 기록 · dedupe 도입** — 순차 upload에서는 `file_count`로 충분하고, 새 영속 경계가 생긴다. 중복이 실제 문제가 되면 연다(계약 §9 Reopen trigger).

## 4. 남긴 것

계약 §9가 소유한다. 모두 Final을 막지 않는다.

- **구현 선행 조건(§9.1)** — 빈 case 생성 · 원본 연결 함수(case, #270) · 202 응답 `running_jobs`에 이번 발주를 `PENDING`으로(case) · 분석 시작 · 중단 command(case) · 원본 파일명 전달 · 등록 실패 taxonomy 세분화 · ref 소유 조회 · DerivedAsset bytes/`Content-Type` 열기(recording) · §5.5 배치에 맞춘 각 계약 문구 정합(recording · case).
- **후속 결정(§9.2)** — `failed_file_count` 의미와 실패 이력 영속 · purge 뒤 ref 의미(RD-10).

## 5. Consumer Review

| 검토자 | 범위 | 결과 |
| --- | --- | --- |
| 신유민 (`web`) | 필수 Consumer — 계약 §6 흐름 | **완료 — Final을 막는 항목 없음** (2026-10-05, [댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#issuecomment-5992194150)). §6 흐름 · §3.2 읽는 순서 · §3.3 envelope · §5.5 · §5.6 그대로 구현 가능. 요청 반영: `http.*` `message_key = code`(§3.3). 질문 ① upload 연결 시 `file_count` +1 여부 → case 답변 「예」로 §5.2에 확인 절차 반영. `failed_file_count`는 쓰지 않음 |
| 유소연 (`case`) | command · CaseView · 빈 case · 202/200 | **완료 — Final을 막는 항목 없음** (2026-10-04, [review](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#pullrequestreview-5406810565) · 2026-10-05 [답변](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#issuecomment-5993309682)). §5.3 · 200/202 기준 · §5.4 동의. 결정: 원본은 `INTAKE`에서만 · 빈 case 값(#270) · `file_count` +1 / `case_rev` 불변 · `contract` 키는 CaseView schema에 등재. 선행 조건 8-11(202 `running_jobs`에 `PENDING`) · 8-12(빈 case)는 case 구현 |
| 정철원 (`recording`) | upload · FrameRef · asset · ref 소유 | **완료 — 방향 동의, 구현 선행 조건 유지** (2026-10-05, [댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#issuecomment-5991448683) · [`failed_file_count`](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/265#issuecomment-5991524900)). §5.2 응답 시점 · `filename` 별도 전달 · §5.5 composition root `read_frame` 배치 · §3.5 소유 검사 동의. 요청 반영: 422/503은 recording 실패 종류로만 매핑, ffprobe 세부 분류는 recording 후속. §5.6은 방향 동의 · DerivedAsset read capability와 소유 조회를 §9.1에 유지. 손상 영상 전부 `201 + UNAVAILABLE` 안은 미확정으로 보류 → §9.2 |
