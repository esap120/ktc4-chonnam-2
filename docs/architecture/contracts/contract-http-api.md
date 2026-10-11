# Contract — HTTP API (web ↔ api)

**Status:** `Final — Accepted`

**Accepted:** 2026-10-05 · web Consumer review · case · recording boundary review(PR #265)를 반영해 `http-api/v0`(Draft)에서 `http-api/v1`(Final)로 승격(§10). 리뷰 결과는 짝 ADR §5가 기록한다. §9의 항목은 구현 선행 조건 · 후속 결정이며 Final을 막지 않는다.

**Architecture Contract:** §5-1 목록 밖의 transport 계약 — 운반 대상은 v4 §5-1 ⑪ `CaseView`(read)와 case-command(write). 배포 단위 「API 1」(`../module-architecture.md` §1-5)

**Contract Version:** `http-api/v1`

> **`http-api/v1` 변경 (2026-10-05, PR #265 리뷰 반영 — 유소연 · 정철원 · 신유민 리뷰, 김준영 결정).** endpoint · envelope · 200/202 기준은 v0 그대로다. ① `POST /sources`는 case가 `INTAKE`일 때만 받는다 — 아니면 `409 http.source_not_allowed`(§3.4 · §5.2) ② upload 실패는 recording이 돌려준 실패 종류로만 `422`(결정적 거부) / `503`(일시 장애)로 나눈다(§5.2) ③ `http.*`의 `message_key` = `error.code`(§3.3) ④ upload 응답을 받지 못했을 때 `manifest_summary.file_count`로 반영 여부를 확인한다(§5.2) ⑤ web은 `failed_file_count`를 화면 판단에 쓰지 않는다(§5.2) ⑥ 빈 case 예시를 case 결정 값으로 맞춤(§5.1) ⑦ §9를 구현 선행 조건과 후속 결정으로 나눔.

**Producer / Owner:** `api` composition root — 김준영 · **Consumer:** `web` — 신유민(필수 Consumer review) · **Boundary review:** `case` — 유소연(command · CaseView · 빈 case 생성) · `recording` — 정철원(upload · FrameRef · asset · ref 소유 경계)

**Decision:** [#247](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/247) RD-05 (ACCEPTED 2026-10-04) · 입력 [#245](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/245)(dispatch transaction · 중단) · [#246](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/246)(upload publish 순서 · persistent ref)

**Related ADR:** `adr/adr-http-api.md` (Accepted)

---

## 1. 목적과 경계

web이 backend를 부르는 HTTP 경로 · status · header · body를 정한다. HTTP는 **이미 있는 Domain Contract를 옮기는 transport**다.

- web은 domain 의미를 다시 계산하지 않는다. 화면은 CaseView만 보고 그린다(CaseView 계약 B절 §1).
- HTTP 층은 case 의미를 재해석하지 않는다. command `kind` · CaseView 내용 · `error.code`를 보고 판단하지 않고, 이 문서의 표만 조회한다.
- Runtime 내부(`JobExecution` · queue · lease · attempt)는 HTTP로 나가지 않는다. 진행은 CaseView의 `running_jobs[]` · `progress[]`로만 보인다(`contract-job-execution.md` §2).

### 1.1 authority — 무엇이 어디에 있나

| 대상 | authority | 이 문서가 하는 일 |
| --- | --- | --- |
| command 요청 · 응답 · `error.code` | [`contract-case-command.md`](../../modules/case/contracts/contract-case-command.md)(`case-command/v0` Draft, case 소유) | 경로 · status 매핑만 붙인다. body는 그대로 |
| CaseView 모양 · `running_jobs[]` 의미 | [`contract-job-record-case-view.md`](./contract-job-record-case-view.md) B절(`case-view/v1.6`) | JSON 그대로 전달 |
| SourceAsset · FrameRef · 자산 실패 code | [`contract-source-asset-media-stream.md`](./contract-source-asset-media-stream.md) §3 · §5 · §6.6 | ref를 받아 bytes로 돌려주는 HTTP 모양 |
| DerivedAsset · 자산 lifecycle | [`contract-analysis-source-derived.md`](./contract-analysis-source-derived.md) §7 · §8 | 다운로드 응답 모양 |
| ReportPackage 존재 조건 | [`contract-requirement-report-package.md`](./contract-requirement-report-package.md) §8.1 · §8.4 | — |
| dispatch transaction · 중단 | [Runtime Tech Spec](../../runtime/runtime-tech-spec.md) §12.1 · §12.5 | 202 / 200 판단 근거 |
| upload publish 순서 · persistent ref | [Ops Spec](../../runtime/ops-spec.md) §4-2 | 응답 시점 |
| health 의미 | Runtime Tech Spec §14 · Ops Spec §9 | 응답 모양 |

이 문서가 새로 정하는 것은 **HTTP에만 있는 의미**(경로 · status · header · multipart field · `http.*` 오류 · ref 소유 검사 결과)다. 위 계약의 필드를 추가 · 삭제 · 이름 변경하지 않는다.

## 2. Endpoint

| Method | Path | 성공 status | 응답 body | authority |
| --- | --- | --- | --- | --- |
| `POST` | `/cases` | `201` | `{case_id, case_view}` | 이 문서 · CaseView |
| `POST` | `/cases/{case_id}/sources` | `201` | `{case_id, source_asset_ref, case_view}` | 이 문서 · SourceAsset · CaseView |
| `POST` | `/cases/{case_id}/commands` | `202` · `200` | case-command 응답 그대로 | case-command |
| `GET` | `/cases/{case_id}/view` | `200` | CaseView 그대로 | CaseView |
| `GET` | `/cases/{case_id}/frames/{frame_ref}` | `200` | 이미지 bytes | FrameRef |
| `GET` | `/cases/{case_id}/assets/{asset_ref}` | `200` | 파일 bytes | DerivedAsset · ReportPackage |
| `GET` | `/health/live` | `200` | `{status}` | Tech Spec §14 |
| `GET` | `/health/ready` | `200` · `503` | `{status}` | Tech Spec §14 |

- **이 밖의 endpoint는 없다.** job 상태 endpoint는 두지 않는다 — web은 JobExecution을 읽지 않는다. 분석 시작 · 중단 · 선택 같은 domain action은 route가 아니라 `/commands`의 `kind`다(#247 H-2).
- web이 따라가는 순서는 §6이다.

## 3. 공통 규칙

### 3.1 경로 · 직렬화

- 경로는 API base URL 기준이다. base URL · 앞 경로(prefix) · domain · TLS는 배포가 정한다(RD-12 · RD-14). 경로에 version을 넣지 않는다.
- `case_id` · `frame_ref` · `asset_ref`는 **서버가 발급한 opaque 문자열**이다. web은 CaseView · 응답에서 받은 값을 그대로 쓰고, path segment로 넣을 때 percent-encoding만 한다. prefix(`fr_` · `da_`)나 문자열을 파싱하지 않는다(`contract-source-asset-media-stream.md` §2). 실제 `case_id` 형식은 case가 정한다(현재 `case_` + uuid4 hex 32자, [#270](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/270)). §5.3 이후 예시의 `case_h001` 같은 짧은 id는 fixture 표기다.
- JSON body는 `application/json`, UTF-8이다. 필드 이름 · 값은 authority 계약 그대로다.

### 3.2 web이 응답을 읽는 순서

1. **status로 분기한다.** 2xx면 그 endpoint의 성공 body(§5), 아니면 §3.3 envelope이다.
2. `/commands`만 예외적으로 404 · 409 · 422 body도 case-command 응답이다 — 모양이 envelope과 같으므로 web은 같은 코드로 읽는다.
3. 화면은 body의 `case_view`로 그린다. status는 「이 요청이 어떻게 끝났나」만 말하고 화면 상태를 대신하지 않는다.

### 3.3 Error envelope

2xx가 아닌 JSON 응답은 모두 이 모양이다 — 예외는 `/health/*`뿐이다(§5.7). **case-command 응답과 같은 모양**이다(#247 H-6).

```json
{
  "ok": false,
  "error": { "code": "string", "message_key": "string" },
  "case_view": "CaseView | null"
}
```

- `/commands`가 case 판단으로 실패하면(§5.3) body는 case가 만든 그대로다 — `error.code`는 `case.command.*`, `case_view`는 case가 실은 값이다. HTTP 층이 code를 바꾸거나 덮지 않는다.
- 그 밖의 오류는 HTTP 층이 만든다 — `error.code`는 §3.4의 `http.*`, `case_view`는 항상 `null`이다.
- **`http.*` 오류의 `message_key`는 `error.code`와 같은 문자열이다.** 화면 문구는 web이 code별로 연결한다. `case.command.*`의 `message_key`는 case-command가 정하며(case-command §9) 이 문서는 정하지 않는다.
- frames · assets처럼 성공 body가 bytes인 endpoint도 오류는 이 JSON이다.
- 프레임워크 기본 오류 body(예: FastAPI `{"detail": ...}`)를 내보내지 않는다. path · body 검증 오류도 이 envelope으로 바꾼다.

### 3.4 Status 매핑

같은 종류의 오류는 endpoint와 무관하게 같은 status다.

| status | 언제 | `error.code` | endpoint |
| --- | --- | --- | --- |
| `200` | 조회 성공 · command 성공(발주 없음) | — | commands · view · frames · assets · health |
| `201` | case 생성 · source 등록 성공 | — | cases · sources |
| `202` | command 성공 + 이번 command로 JobRecord ≥ 1건 발주 | — | commands |
| `400` | transport 형식 오류 — JSON · multipart를 파싱할 수 없음 · 필수 part 누락 · path와 body의 `case_id` 불일치 | `http.malformed_request` | sources · commands |
| `404` | case 없음 · ref 없음 · **ref가 이 case 소유가 아님**(§3.5) · 정의되지 않은 경로 | `http.not_found` | 모든 `/cases/{case_id}/…` |
| `404` | command 대상 case 없음(`unknown_target`이고 `case_view=null`) | `case.command.unknown_target` | commands |
| `404` | ref는 이 case 소유지만 지금 bytes를 줄 수 없음 | `http.ref_unavailable` | frames · assets |
| `405` | 경로는 있지만 method가 없음 | `http.method_not_allowed` | 전체 |
| `409` | 지금 case 상태에서 할 수 없음 — `stale_revision` · `not_allowed` · `unknown_target`(`case_view` non-null) · 표에 없는 그 밖의 `ok:false` | `case.command.*` 그대로 | commands |
| `409` | case가 지금 원본 연결을 받지 않음 — 원본은 `INTAKE`에서만 추가한다(§5.2) | `http.source_not_allowed` | sources |
| `413` | request body가 서버 한도를 넘음 | `http.payload_too_large` | sources · commands |
| `415` | request `Content-Type`이 endpoint가 받는 형식이 아님 | `http.unsupported_media_type` | sources · commands |
| `422` | 형식은 맞지만 domain이 내용을 거부 | `case.command.invalid_payload` | commands |
| `422` | 형식은 맞지만 recording이 이 입력을 결정적으로 등록할 수 없다고 판정 — 영상이 아님 · 지원하지 않는 구조(§5.2) | `http.source_rejected` | sources |
| `500` | 예기치 못한 서버 오류 | `http.internal_error` | 전체 |
| `503` | 필수 dependency(DB · Runtime enqueue · 공유 저장소 · recording 등록 도구)를 지금 쓸 수 없음 — 요청은 반영되지 않았다 | `http.dependency_unavailable` | 전체(`/health/*`는 §5.7) |

- **404가 code 두 개인 이유.** `/commands`는 case 응답 body를 보존하므로 case의 code를 그대로 싣는다. 다른 endpoint의 「case 없음」은 HTTP 층이 판단하므로 `http.not_found`다. status는 같다.
- **422의 기준.** request가 transport로서 올바르게 도착했고, 그 내용을 domain(case) 또는 capability(recording)가 거부했다. 400은 transport 단계에서 이미 읽을 수 없는 경우다. HTTP 층은 command body의 모양을 검사하지 않으므로(§5.3) command 모양 오류는 400이 아니라 case의 `invalid_payload` → 422다.
- **`410 Gone`은 쓰지 않는다.** 「있었는데 사라짐」을 영구적이라고 말할 근거가 현재 계약에 없다 — `availability=UNAVAILABLE`은 「존재하지 않거나 접근 · decode할 수 없음」을 함께 뜻한다(`contract-source-asset-media-stream.md` §3.5). 영구성을 모르면 404다. purge 뒤 ref 의미가 RD-10에서 정해지면 다시 본다(§9.2).
- **409가 두 종류인 이유.** `/commands`의 409는 case 응답 body(`case_view` 포함)를 그대로 싣는다. `/sources`의 409는 HTTP 층이 만드는 `http.*`라 `case_view=null`이다 — web은 `GET /view`로 현재 화면을 다시 읽는다. 같은 파일이 `INTAKE`에서는 받아지므로 내용 거부(422)가 아니라 상태 충돌(409)이다.
- **재시도.** `503`은 반영되지 않았으므로 같은 요청을 다시 보내도 된다. `500`이나 응답을 받지 못한 경우는 반영 여부를 모른다 — `POST`를 다시 보내기 전에 `GET /cases/{case_id}/view`를 다시 읽는다. `/sources`는 `manifest_summary.file_count`로 판단한다(§5.2). 재시도 간격은 web 구현값이다.

### 3.5 Resource isolation

- `/cases/{case_id}/…` 아래의 ref는 **그 case에 속할 때만** 응답한다. 속하지 않으면 그 ref가 다른 case에 실제로 있든 없든 `404 http.not_found`다 — 다른 case의 ref 존재 여부를 응답으로 드러내지 않는다.
- 「속한다」는 recording의 case↔asset 연결(Ops Spec §4-2 metadata)로 판단한다.
  - `frame_ref` — 그 FrameRef의 `media_stream_ref`(`contract-source-asset-media-stream.md` §5.1)가 이 case에 연결된 SourceAsset의 MediaStream이다.
  - `asset_ref` — 그 DerivedAsset이 이 case에 연결된 자산이다. `purge_case(case_id)`가 case 단위로 파생물을 정리하므로(`contract-analysis-source-derived.md` §8 · §8.1) recording은 case → 자산 연결을 알아야 한다.
- 소유 검사는 api composition root가 recording 조회로 한다. web · case가 대신 하지 않고, ref 문자열로 추론하지 않는다. 그 조회 capability는 아직 공개되지 않았고 모양은 recording 구현 범위다(§9.1 구현 선행 조건).

### 3.6 인증

인증 · 인가 방식은 이 문서 범위 밖이다(Architecture §1-7 A2 별도 결정). 이 문서의 경로는 인증 없이도 성립하게 설계했다.

- 인증이 정해지기 전까지는 `case_id`를 아는 것이 사실상 접근 조건이다. 이 위험은 A2에서 다룬다.
- frames · assets는 브라우저가 `<img src>` · 다운로드 링크로 직접 여는 것을 전제한다(추가 header 없음). A2 결정이 이 전제를 바꾸면 이 문서를 다시 연다.

## 4. HTTP가 정의하지 않는 것

이 문서에 넣지 않는다 — 각 SoT가 소유한다.

| 항목 | 소유 |
| --- | --- |
| DB schema · UoW · transaction API 모양 | Tech Spec §12.1 · 구현 플래닝 |
| Worker polling · lease · heartbeat · retry · backoff | Tech Spec §4 ~ §7 · workflow §6 |
| upload body 한도 · frame cache 수명 · ready 검사 제한 시간 **숫자** | workflow §6 Provisional Baseline |
| web polling interval | web 구현값 |
| filesystem host path · Compose 표기 | RD-12a |
| FrameRef를 bytes로 둘지 원본+위치로 재생성할지 | recording 구현(#246 S-4) |
| FastAPI `def` / `async def` · middleware 배치 | 구현(#247 H-5 · RD-01j) |
| web component state · 화면 문구 | web |
| 공개 domain · TLS · reverse proxy · CORS | RD-14 |
| 인증 방식 | Architecture A2 |
| 보관 기간 · purge 정책 | RD-10 |

## 5. Endpoint 상세

### 5.1 `POST /cases` — 빈 case 생성

**Request**

- body 없음. 서버는 body를 읽지 않는다. client가 `case_id`를 만들어 보내지 않는다.

**성공 — `201 Created`**

- `Location: /cases/{case_id}/view`
- body:

  | 필드 | 타입 | 의미 |
  | --- | --- | --- |
  | `case_id` | string | 서버가 발급한 case identity. `case_view.case_id`와 같다 |
  | `case_view` | CaseView | 생성 직후 `case.get_view()` 결과. 빈 case의 각 값은 case가 정한다 |

- 영상 · 기억 단서(`hints`)는 여기서 받지 않는다. 영상은 §5.2, 단서는 분석 시작 command(case-command, case가 추가 — §9.1)로 들어간다.

**Errors:** `503` · `500`

```http
POST /cases HTTP/1.1
Content-Length: 0
```

```http
HTTP/1.1 201 Created
Location: /cases/case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987/view
Content-Type: application/json
```

```json
{
  "case_id": "case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987",
  "case_view": {
    "case_id": "case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987",
    "case_rev": 1,
    "stage": "INTAKE",
    "user_reviewed": false,
    "manifest_summary": { "file_count": 0, "ok_file_count": 0, "failed_file_count": 0, "duration_sec": 0, "range": null },
    "hints": { "time": null, "vehicle": null, "situation": null, "location": null },
    "progress": [
      { "step": "file_intake", "state": "PENDING" },
      { "step": "coarse_search", "state": "PENDING" },
      { "step": "candidate_review", "state": "PENDING" },
      { "step": "plate_read", "state": "PENDING" },
      { "step": "overlay_time_read", "state": "PENDING" },
      { "step": "evidence_assembly", "state": "PENDING" },
      { "step": "requirement_check", "state": "PENDING" },
      { "step": "package_assembly", "state": "PENDING" }
    ],
    "candidates": [],
    "evidence": null,
    "requirements_evidence": null,
    "requirements_package": null,
    "package": null,
    "running_jobs": [],
    "notices": []
  }
}
```

- 위 값은 case가 정한 빈 case 초기값이다([#270](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/270), case `decisions/empty-case-and-manifest.md`) — `case_rev=1` · `INTAKE` · `hints` 네 키 `null` · `manifest_summary` 0 · `range:null` · `progress`는 8단계 전부 `PENDING`(CaseView 계약 B절 `progress[]` step 집합 규칙 1, `file_intake`는 분석 시작 뒤 `DONE`). 값의 authority는 case이고, 이 문서는 그대로 전달한다.

```json
// 503 — DB를 쓸 수 없어 case를 만들지 못함
{ "ok": false, "error": { "code": "http.dependency_unavailable", "message_key": "http.dependency_unavailable" }, "case_view": null }
```

### 5.2 `POST /cases/{case_id}/sources` — 원본 영상 1개 등록

**Request**

- `Content-Type: multipart/form-data`
- part는 **`file` 하나만** 받는다 — 1 request = 1 file(#247 H-5). `file` part가 없거나 둘 이상이거나, 다른 이름의 part가 있으면 `400`. 이 버전에는 metadata field가 없다.
- `file` part의 `filename` parameter는 필수다. 서버는 이 값을 **사용자 원본 파일명**으로 recording 등록에 넘긴다 — recording이 파일명에서 시각 출처를 찾는 입력이다(`contract-recording-timeline-asset-span.md` `FILENAME` 출처). HTTP 층은 이 값을 파싱 · 검증하지 않고, 저장 경로로 쓰지 않는다. 저장 위치는 서버가 정한다.
- part의 `Content-Type`과 확장자로 영상 여부를 판단하지 않는다. 판단은 recording 등록이 한다.
- 여러 파일은 파일마다 요청을 따로 보낸다. 요청마다 성공 · 실패가 따로 나고 실패한 파일만 다시 보낼 수 있다(#247 H-5). baseline web 흐름은 **한 번에 하나씩 순서대로** 보낸다 — 아래 「응답을 받지 못했을 때」가 이 순서를 전제로 한다.
- **원본은 `INTAKE`에서만 추가한다.** 분석 시작 뒤 추가 upload는 받지 않는다 — 판단은 case다(case 결정, PR #265 case review · [#270](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/270)). case가 연결을 거부하면 `409 http.source_not_allowed`이고 recording 등록도 같은 transaction에서 rollback된다. bytes를 다 받기 전에 먼저 거르는지는 구현이며, 결과 status · code는 같다.

**처리 — 응답 전에 끝낸다**

```text
case 존재 확인
→ 같은 mount의 staging에 bytes 기록 → fsync
→ 같은 mount의 final 위치로 publish
→ recording 등록 · 이 case와의 연결 commit
→ 201
```

- 순서와 저장 경계는 Ops Spec §4-2(#246 S-2)다. bytes를 다 받은 것만으로 성공 응답하지 않는다.
- `201`이면 `source_asset_ref`는 persist됐고, Worker가 api · worker restart 뒤에도 다시 등록하지 않고 dereference할 수 있다(#246 S-4 · S-5).
- 실패하면 SourceAsset 등록도 case 연결도 남지 않는다. publish된 파일이나 staging 파일이 row 없이 남을 수 있고 정리는 workflow §6 값이다.
- 같은 파일을 다시 올리면 새 SourceAsset이다(#246 S-5). 이 버전에는 idempotency key · upload 시도 기록 · dedupe가 없다.

**등록 실패 분류 — `422` / `503`**

| 경우 | status · code | 등록 · 연결 | 다시 보내면 |
| --- | --- | --- | --- |
| recording이 이 입력을 결정적으로 등록할 수 없다고 판정 — 영상이 아님 · recording이 지원하지 않는 구조 | `422 http.source_rejected` | 남지 않음 | 같은 결과 |
| 일시 장애 — 공유 저장소 · ffprobe 등 도구 · recording dependency · DB | `503 http.dependency_unavailable` | 남지 않음 | 될 수 있음 |

- **구분은 recording이 돌려준 실패 종류로만 한다** — 결정적 거부(`UNSUPPORTED_MEDIA`)는 `422`, 일시 실패(`TEMPORARY_FAILURE`)는 `503`. 두 종류 밖의 실패는 `500`이다. HTTP 층은 예외 메시지 · 파일 내용 · 도구 출력으로 분류를 추론하지 않는다.
- 현재 recording 등록은 ffprobe 실패를 손상 · 미지원 입력과 일시 장애 구분 없이 `TEMPORARY_FAILURE`로 낸다. 그 동안 그런 파일은 `503`으로 나간다 — 세부 분류는 recording 구현 후속이다(§9.1). 이 문서의 매핑은 바뀌지 않는다.
- 등록은 됐지만 접근 · decode할 수 없는 원본은 recording 판단으로 `201` + `availability=UNAVAILABLE`일 수 있다(`contract-source-asset-media-stream.md` §3.5). 손상 영상을 모두 `201`로 등록한다는 뜻은 아니다.

**실패한 파일 표시**

- 업로드 직후 실패한 파일은 web이 **자기가 보낸 파일명과 실패 응답을 짝지어** 표시한다(`core-user-flow.md` §23 「일부 영상을 처리할 수 없습니다」). CaseView에는 파일별 목록이 없다.
- web은 `manifest_summary.failed_file_count`를 화면 판단에 쓰지 않는다. 거부된 upload는 등록 · 연결을 남기지 않으므로 case가 셀 수 없다 — 의미는 후속 결정이다(§9.2).
- 새로고침 뒤 실패 파일 목록 복원은 MVP 범위 밖이다. 사용자는 실패한 파일을 다시 고른다.

**응답을 받지 못했을 때 — `file_count`로 확인**

`POST /sources`의 응답이 오지 않거나 `500`이라 반영 여부를 모르면, 다시 보내기 전에 아래 순서를 따른다. 보내기 전 `manifest_summary.file_count`를 `N`이라 한다(직전에 받은 `case_view` 값).

1. `GET /cases/{case_id}/view`를 읽는다.
2. `file_count == N + 1`이면 이미 등록 · 연결됐다 — **다시 보내지 않는다.**
3. `file_count == N`이면 반영되지 않았다 — 다시 보낸다.

- 근거는 case 규칙이다 — recording이 등록 · 연결한 원본마다 `file_count`가 `availability`와 무관하게 +1이고, 같은 transaction이라 `201`이면 이미 반영돼 있다(PR #265 case 답변 · [#270](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/270)).
- **확인 기준은 `case_rev`가 아니라 `file_count`다.** upload는 `case_rev`를 올리지 않는다(같은 case 규칙).
- 파일을 한 번에 하나씩 보낼 때만 정확하다. 동시에 여러 파일을 보내면 어느 파일이 반영됐는지 구분할 수 없다.

**성공 — `201 Created`**

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `case_id` | string | path의 `case_id` |
| `source_asset_ref` | string | 이 파일의 `SourceAsset.source_asset_ref`(`contract-source-asset-media-stream.md` §3.2). upload 1건 = 물리 파일 1개 = SourceAsset 1개다. web은 요청과 결과를 짝짓는 데만 쓰고, 이 버전에 이 값을 받는 endpoint는 없다 |
| `case_view` | CaseView | 등록 · 연결 commit 뒤 `case.get_view()` 결과. upload가 `manifest_summary`를 어떻게 바꾸는지는 case가 정한다(위 「응답을 받지 못했을 때」가 쓰는 `file_count` 규칙 포함) |

- MediaStream ref는 돌려주지 않는다. stream 구성은 web이 쓰지 않는다.
- 업로드 직후 보여 줄 영상 사실(촬영 시각 · 화면 시각 표시 · GPS 유무, `core-user-flow.md` §5 `[프로토타입]`)은 이 응답에 따로 싣지 않는다. CaseView 계약에 들어가면 `case_view`로 온다.

**Errors**

| status | code | 경우 |
| --- | --- | --- |
| `400` | `http.malformed_request` | multipart 파싱 불가 · `file` part 0개 또는 2개 이상 · 다른 part 있음 · `filename` 없음 |
| `404` | `http.not_found` | `case_id` 없음 |
| `409` | `http.source_not_allowed` | case가 `INTAKE`가 아님 — 분석 시작 뒤 추가 upload. 등록 · 연결이 남지 않는다 |
| `413` | `http.payload_too_large` | body가 서버 한도를 넘음. 한도 값은 workflow §6이고 이 문서에 없다 |
| `415` | `http.unsupported_media_type` | request `Content-Type`이 `multipart/form-data`가 아님 |
| `422` | `http.source_rejected` | recording이 결정적으로 등록할 수 없다고 판정(위 분류). 같은 파일을 다시 보내도 결과가 같다 |
| `503` | `http.dependency_unavailable` | DB · 공유 저장소 · recording 등록 도구의 일시 장애(위 분류). 다시 보내도 된다 |
| `500` | `http.internal_error` | 예기치 못한 오류 · 위 두 분류 밖의 등록 실패 |

```http
POST /cases/case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987/sources HTTP/1.1
Content-Type: multipart/form-data; boundary=----daesingo

------daesingo
Content-Disposition: form-data; name="file"; filename="20260824_180000_EVT_1.mp4"
Content-Type: video/mp4

<binary>
------daesingo--
```

```json
// 201
{
  "case_id": "case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987",
  "source_asset_ref": "sa_01JREC000000000000000001",
  "case_view": { "case_id": "case_3f2a9c0e8b7d4e1fa6c5b4d3e2f10987", "case_rev": 1, "stage": "INTAKE",
                 "manifest_summary": { "file_count": 1, "ok_file_count": 1, "failed_file_count": 0, "duration_sec": 0, "range": null },
                 "...": "..." }
}
```

```json
// 422 — 등록할 수 있는 영상이 아님
{ "ok": false, "error": { "code": "http.source_rejected", "message_key": "http.source_rejected" }, "case_view": null }
```

```json
// 409 — 분석 시작 뒤 추가 upload
{ "ok": false, "error": { "code": "http.source_not_allowed", "message_key": "http.source_not_allowed" }, "case_view": null }
```

### 5.3 `POST /cases/{case_id}/commands` — case command

**Request**

- `Content-Type: application/json`
- body는 **case-command 요청 그대로**다(`case_id` · `expected_case_rev` · `kind` · `payload`, case-command §4). 새 command schema를 만들지 않는다.
- HTTP 층은 body 모양을 검사하지 않는다. JSON으로 파싱되면 그대로 `case.handle_command()`에 넘긴다 — 키 누락 · 모르는 `kind` · payload 오류는 case가 `invalid_payload`로 판정한다.
- 예외는 하나다 — body가 object이고 `case_id`가 문자열인데 path의 `case_id`와 다르면 `400`. 경로와 body가 서로 다른 case를 가리키는 transport 불일치다.

**처리**

```text
request JSON
→ api composition root transaction 시작
   → case.handle_command()                     — case 판단 · 저장
   → case가 돌려준 「이번 command로 append된 JobRecord 목록」마다 Runtime enqueue
→ commit
→ status 결정(아래 표) → 응답
```

- transaction 경계는 composition root가 소유한다(Tech Spec §12.1, #245 D-2). case 저장이나 enqueue가 실패하면 전체 rollback이고 응답은 `503`이다 — command는 반영되지 않았다(#245 D-3).
- 중단 command는 JobRecord를 발주하지 않고 같은 transaction에서 Runtime cancel을 요청한다(Tech Spec §12.5) — 그래서 `200`이다.

**Status — 표 조회만 한다**

| case 응답 | composition root가 받은 append 목록 | status | body |
| --- | --- | --- | --- |
| `ok:true` | 1건 이상 | `202 Accepted` + `Location: /cases/{case_id}/view` | case-command 응답 |
| `ok:true` | 0건 | `200 OK` | case-command 응답 |
| `ok:false`, `case.command.invalid_payload` | — | `422` | case-command 응답 |
| `ok:false`, `case.command.unknown_target`, `case_view=null` | — | `404` | case-command 응답 |
| 그 밖의 `ok:false` | — | `409` | case-command 응답 |

- **HTTP 층은 `kind`를 보고 200 / 202를 추론하지 않는다.** 같은 `kind`라도 발주 여부에 따라 status가 다를 수 있다. 판단 입력은 case가 composition root에 따로 돌려주는 append 목록이며, 이 목록은 응답 body에 싣지 않는다(case-command 응답은 `ok` · `error` · `case_view`뿐이다).
- 200 · 202 · 404 · 409 · 422의 body는 **같은 schema**(case-command §4 응답)이고, HTTP 층은 필드를 더하거나 빼지 않는다. 성공이면 `case_view`는 이번 command의 변경을 반영한 값이다 — case가 transaction 안에서 만들고, 응답은 commit 뒤에만 나가므로 commit되지 않은 상태를 보이지 않는다.
- **202의 `case_view.running_jobs`에는 이번 command로 append된 job이 들어 있어야 한다.** append된 JobRecord는 case가 결과를 기다리는 job이므로(CaseView 계약 B절 §10 불변조건 5) case projection의 의무다. 이것이 없으면 web이 202를 받자마자 `running_jobs=[]`를 보고 polling을 멈춘다. `case_view`는 enqueue 전에 만들어져 이번 job의 실행 기록이 아직 없으므로, case는 「JobRecord는 있고 실행 기록이 없는 job」을 **`PENDING`**으로 싣는다(PR #265 case review). 현재 `handle_command()`는 `running_jobs`를 호출자에게서 command 전에 받으므로 case가 직접 계산하도록 바꾼다 — case 구현 선행 조건(§9.1). HTTP 층이 body를 고쳐 채우지 않는다.
- **202의 뜻은 「이번 command가 JobRecord를 발주했고 commit됐다」뿐이다.** job이 시작 · 완료됐다는 뜻이 아니고, HTTP 층이 job 식별자를 따로 싣지 않는다(CaseView의 `running_jobs[].job_id`는 CaseView 필드로 온다). 진행은 `case_view.running_jobs[]` · `progress[]`로 본다.
- polling을 할지는 status가 아니라 `case_view.running_jobs`로 정한다(§5.4). `200`이어도 앞서 발주된 job이 남아 있으면 `running_jobs`는 비어 있지 않다.
- case-command가 `error.code`를 추가하면 이 표에 행을 더한다. 행을 더하기 전까지 등재되지 않은 `ok:false`는 `409`다.

**그 밖의 Errors:** `400 http.malformed_request`(JSON 파싱 불가 · path/body `case_id` 불일치) · `413` · `415`(`application/json`이 아님) · `503` · `500` — 모두 §3.3 envelope, `case_view=null`.

```http
POST /cases/case_h001/commands HTTP/1.1
Content-Type: application/json

{ "case_id": "case_h001", "expected_case_rev": 4, "kind": "RUN_NOTICE_ACTION",
  "payload": { "notice_code": "readout.plate_read_failed", "action": "RETRY_PLATE_READ" } }
```

```http
HTTP/1.1 202 Accepted
Location: /cases/case_h001/view
Content-Type: application/json
```

```json
{
  "ok": true,
  "error": null,
  "case_view": {
    "case_id": "case_h001", "case_rev": 5, "stage": "EVIDENCE_REVIEW",
    "running_jobs": [ { "job_id": "job_h001_plate_retry", "kind": "PLATE_READ", "label_key": "job.plate_read", "status": "PENDING" } ],
    "...": "..."
  }
}
```

```json
// 200 — MARK_REVIEWED (case-command §5: user_reviewed=true · case_rev +1, JobRecord 발주 없음)
// 요청: { "case_id": "case_h001", "expected_case_rev": 6, "kind": "MARK_REVIEWED", "payload": {} }
{ "ok": true, "error": null, "case_view": { "case_id": "case_h001", "case_rev": 7, "stage": "READY", "user_reviewed": true, "...": "..." } }
```

```json
// 409 — 화면이 낡음 (case-command §8 예시 모양). 요청의 expected_case_rev가 현재 case_rev와 다르다
{ "ok": false,
  "error": { "code": "case.command.stale_revision", "message_key": "command.stale_revision" },
  "case_view": { "case_id": "case_h001", "case_rev": 7, "...": "..." } }
```

- 위 `case_rev` 증가분은 case 규칙(case-command §5)이고 예시일 뿐이다. 202 예시는 재판독 발주가 JobRecord 1건을 남긴다는 CaseView 계약 B절 §7 매핑을 따른다.

### 5.4 `GET /cases/{case_id}/view` — CaseView polling

**성공 — `200 OK`** · body는 **CaseView 그대로**(`case.get_view()` 결과, `case-view/v1.6`). HTTP 층은 감싸지 않고 필드를 더하거나 빼지 않는다.

**Polling**

- baseline 진행 갱신은 이 endpoint를 반복해서 부르는 것이다. WebSocket · SSE는 baseline이 아니다(Tech Spec §9). interval은 web 구현값이다.
- **`running_jobs`가 `[]`이면 polling을 멈춰도 된다.** `running_jobs[]`는 Runtime의 물리 `RUNNING` 목록이 아니라 **case가 아직 결과를 기다리는 job 목록**이다(CaseView 계약 B절 §10 불변조건 5).
  - 실행 terminal과 case 반영 · 후속 발주 사이, 자동 retry backoff 동안에도 job은 빠지지 않는다 — 그 틈에 polling이 일찍 멈추지 않는다.
  - 사용자 중단 · case timeout 뒤에는 Runtime execution이 협력적 중단 때문에 아직 RUNNING이어도 그 job은 `running_jobs`에서 빠진다(Tech Spec §12.5). web은 이것을 「실행이 끝났다」로 읽지 않고 「case가 더 기다리지 않는다」로 읽는다.
- `running_jobs[].status`는 CaseView projection 값(`PENDING` · `RUNNING`)이다. HTTP는 Runtime의 물리 상태로 다시 해석하거나 보정하지 않는다.
- `ETag` · `304`는 baseline이 아니다.

**Errors:** `404 http.not_found`(case 없음) · `503` · `500`

```http
GET /cases/case_h001/view HTTP/1.1
```

```json
// 200
{ "case_id": "case_h001", "case_rev": 5, "stage": "EVIDENCE_REVIEW", "running_jobs": [], "...": "..." }
```

```json
// 404
{ "ok": false, "error": { "code": "http.not_found", "message_key": "http.not_found" }, "case_view": null }
```

### 5.5 `GET /cases/{case_id}/frames/{frame_ref}` — FrameRef 이미지

CaseView가 노출한 FrameRef — `candidates[].thumb_ref` · `evidence.preview_ref` · `evidence.plate_preview_ref` — 를 이미지로 받는다. web은 recording을 직접 부르지 않는다(`contract-source-asset-media-stream.md` §7). 이 endpoint에서는 **api composition root가 recording `read_frame`을 부른다.** §7은 이미지 경로를 `case → recording frame capability → projection → web`으로 적고 전달 방식은 §9-6 Pending으로 두었다. bytes를 case를 거치지 않고 composition root가 가져오는 이 배치는 recording boundary review에서 승인됐다(PR #265 — 「composition root가 소유를 확인한 뒤 `read_frame`을 부르는 배치에 동의, case가 bytes를 중계할 필요 없음」). FrameRef 자체는 case projection이 고르고 노출하며, 이 배치는 bytes 전달만 정한다. 두 계약의 같은 문구 정합은 각 Owner 몫이다(§9.1).

**성공 — `200 OK`**

- body = 이미지 bytes. 서버가 FrameRef를 정상 dereference했을 때만 보낸다.
- `Content-Type` = 돌려주는 이미지의 실제 형식(예: `image/png`). web은 특정 형식을 가정하지 않는다.
- `Content-Length`를 싣는다.
- `Cache-Control: private` — 공유 cache에 두지 않는다. 같은 `frame_ref`는 다른 frame을 가리키지 않으므로(`contract-source-asset-media-stream.md` §5.2) 브라우저 cache 재사용은 허용한다. `max-age` 값은 workflow §6이다.
- FrameRef를 bytes로 저장했는지 원본+위치로 다시 만드는지는 recording 구현이다(#246 S-4). HTTP 응답은 둘을 구분하지 않는다.

**web이 요청하는 범위**

- web은 **CaseView에 있는 FrameRef만** 요청한다. CaseView에 노출된 FrameRef는 restart 뒤에도 같은 ref로 열린다(#246 S-4).
- 이 case에 속하지만 CaseView에 노출되지 않은 FrameRef의 응답은 보장하지 않는다.

**Errors**

| status | code | 경우 |
| --- | --- | --- |
| `404` | `http.not_found` | case 없음 · `frame_ref` 없음(recording `UNKNOWN_REF`) · 이 case에 속하지 않음(§3.5) |
| `404` | `http.ref_unavailable` | 이 case의 FrameRef지만 지금 이미지를 만들 수 없음 — recording `FRAME_NOT_FOUND` · `STREAM_UNAVAILABLE` · `OUT_OF_RANGE`(`contract-source-asset-media-stream.md` §6.6) |
| `503` | `http.dependency_unavailable` | recording `TEMPORARY_FAILURE` · DB를 쓸 수 없음 |
| `500` | `http.internal_error` | 예기치 못한 오류 |

```http
GET /cases/case_h001/frames/fr_01JREC000000000000000001 HTTP/1.1
```

```http
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: 182344
Cache-Control: private

<binary>
```

```json
// 404 — 다른 case의 frame_ref를 넣음(존재 여부를 드러내지 않음)
{ "ok": false, "error": { "code": "http.not_found", "message_key": "http.not_found" }, "case_view": null }
```

### 5.6 `GET /cases/{case_id}/assets/{asset_ref}` — 신고용 파일 다운로드

최종 신고용 artifact를 받는다. 대표 흐름은 handoff 화면의 `[신고용 영상 다운로드]`(`core-user-flow.md` §21)다.

**`asset_ref`가 오는 곳**

- `asset_ref` = **`CaseView.package.artifact_ref`** 값이다. 이 값은 `ReportPackage.assets.report_video_ref`의 ref, 즉 `derived_role=REPORT_VIDEO`인 DerivedAsset의 `derived_asset_ref`다(`contract-requirement-report-package.md` §8.4 · `contract-analysis-source-derived.md` §7.3).
- 이 endpoint는 path 값을 DerivedAsset ref로 다룬다. prefix로 종류를 추론하지 않는다 — endpoint가 종류를 정한다.
- CaseView가 v1.6에서 노출하는 다운로드 ref는 `package.artifact_ref` 하나다. `plate_image_ref` 등 다른 DerivedAsset을 web에 노출할지는 CaseView 계약이 정하며, 노출되면 같은 endpoint로 받는다.

**생성 전 · 사라진 뒤**

- **생성 전에는 요청할 ref가 없다.** ReportPackage는 신고용 영상이 있어야만 존재하고(`contract-requirement-report-package.md` §8.1), `package`가 `null`이면 `artifact_ref`도 없다. 준비 중 · 실패는 CaseView의 `running_jobs` · `notices`가 보여 준다. 그래서 「생성 전」을 위한 `409`나 대기 응답은 두지 않는다.
- **이 case의 DerivedAsset이지만 bytes를 줄 수 없으면** — `availability=UNAVAILABLE`, 보관 정책으로 정리됨 등 — `404 http.ref_unavailable`이다. 영구 삭제인지 일시 접근 불가인지 현재 계약으로는 구분할 수 없으므로 `410`은 쓰지 않는다(§3.4).

**성공 — `200 OK`**

- body = 파일 bytes.
- `Content-Type` = DerivedAsset의 실제 형식(예: 신고용 영상 `video/mp4`). 형식은 recording export가 정한다.
- `Content-Length`를 싣는다.
- `Content-Disposition: attachment; filename="<저장 이름>"` — 저장 이름은 서버가 정하는 ASCII 파일명이고 확장자는 `Content-Type`과 맞는다. 사용자 원본 파일명 · 차량번호 같은 개인정보를 넣지 않는다. web은 이 이름을 파싱하거나 domain 식별자로 쓰지 않는다.
- `Cache-Control: private, no-store`.
- Range 요청(`206`)은 계약하지 않는다. 구현이 지원해도 되고 web은 의존하지 않는다.

**Errors**

| status | code | 경우 |
| --- | --- | --- |
| `404` | `http.not_found` | case 없음 · `asset_ref` 없음(`UNKNOWN_REF`) · DerivedAsset이 아님(`INVALID_REF_KIND`) · 이 case에 속하지 않음(§3.5) |
| `404` | `http.ref_unavailable` | 이 case의 DerivedAsset이지만 지금 bytes를 줄 수 없음 |
| `503` | `http.dependency_unavailable` | recording `TEMPORARY_FAILURE` · DB를 쓸 수 없음 |
| `500` | `http.internal_error` | 예기치 못한 오류 |

```http
GET /cases/case_h001/assets/da_h001_report_video HTTP/1.1
```

```http
HTTP/1.1 200 OK
Content-Type: video/mp4
Content-Length: 52428800
Content-Disposition: attachment; filename="daesingo_report_video.mp4"
Cache-Control: private, no-store

<binary>
```

```json
// 404 — 이 case의 신고용 영상이지만 더 이상 받을 수 없음
{ "ok": false, "error": { "code": "http.ref_unavailable", "message_key": "http.ref_unavailable" }, "case_view": null }
```

### 5.7 `GET /health/live` · `GET /health/ready`

| endpoint | 뜻 | 확인하는 것 | 확인하지 않는 것 |
| --- | --- | --- | --- |
| `/health/live` | API process가 살아 있고 HTTP 요청을 처리할 수 있다 | process가 응답함 | DB · 저장소 · 외부 provider |
| `/health/ready` | 실제 traffic을 받을 준비가 됐다 | startup 완료(config 검증 · composition root 조립 — 실패하면 process가 뜨지 않는다, RD-07 fail-fast) · DB 연결 · 공유 저장소 mount 사용 가능(Ops §4-2) | 외부 AI provider(Search 등) 호출 · Worker 생존(Runtime DB heartbeat로 따로 본다) · queue 적체 |

- `ready`는 유료 외부 API를 부르지 않는다. provider 장애가 API down으로 읽히지 않게 한다(Tech Spec §14 · Ops §9).
- body는 envelope이 아니라 아래 모양이다. 어느 dependency가 실패했는지는 body에 싣지 않고 서버 로그에 남긴다.

| 응답 | status | body |
| --- | --- | --- |
| live 정상 | `200` | `{ "status": "ok" }` |
| ready 정상 | `200` | `{ "status": "ok" }` |
| ready 준비 안 됨 | `503` | `{ "status": "unavailable" }` |

- 검사 제한 시간은 workflow §6 · 구현값이다. alert · restart 기준은 Ops Spec §9가 소유한다.

```http
GET /health/ready HTTP/1.1
```

```json
// 503
{ "status": "unavailable" }
```

## 6. web 흐름 — 이 계약만으로 구현하는 순서

```text
1. POST /cases                               → 201 {case_id, case_view}
2. INTAKE에서, 파일을 하나씩 순서대로
   POST /cases/{case_id}/sources              → 201 {case_id, source_asset_ref, case_view}
                                                422 · 503은 보낸 파일명과 짝지어 표시 · 503만 다시 보냄
                                                응답 없음 · 500 → GET /view의 file_count로 확인(§5.2)
3. POST /cases/{case_id}/commands             → 202 또는 200, body = case-command 응답
   (분석 시작 kind — case-command)
4. case_view.running_jobs ≠ [] 인 동안
   GET /cases/{case_id}/view 반복             → 200 CaseView
5. CaseView의 FrameRef마다
   GET /cases/{case_id}/frames/{frame_ref}    → 200 image
6. 결과 화면 command (선택 · 상황 응답 · 확인 · 재시도)
   POST /cases/{case_id}/commands             → 202 / 200 / 409(화면이 낡음 → body의 case_view로 다시 그림)
7. case_view.package.artifact_ref가 있으면
   GET /cases/{case_id}/assets/{artifact_ref} → 200 file
```

- 각 단계에서 web이 판단하는 것은 status 분기와 `running_jobs`가 비었는지뿐이다. 무엇을 그릴지는 매번 받은 `case_view`가 정한다.

## 7. 불변조건

1. 2xx JSON 응답의 `case_view`는 그 요청의 변경을 반영한 CaseView이고, 응답은 commit 뒤에만 나간다. `/cases` · `/sources`는 commit 뒤 `case.get_view()`, `/commands`는 case-command 응답의 `case_view` 그대로다. 실패 응답의 `case_view`는 case-command가 정한 값(case 실패)이거나 `null`(`http.*`)이다.
2. `202` 응답의 `case_view.running_jobs`는 비어 있지 않다(§5.3).
3. HTTP status는 §3.4 · §5.3 표 조회로만 정한다. command `kind` · CaseView 필드 값을 보고 정하지 않는다.
4. case-command 응답 · CaseView는 필드 추가 · 삭제 · 이름 변경 · 값 변환 없이 전달한다. `error.code`를 덮지 않는다.
5. `http.*` code는 HTTP 층만 만들고, case가 만든 응답에는 섞이지 않는다.
6. `POST /sources`의 `201`은 recording 등록과 case 연결이 commit된 뒤에만 나간다. 실패 응답 뒤에는 등록 · 연결이 남지 않는다.
7. `POST /sources`는 case가 `INTAKE`일 때만 `201`이다. 그 밖의 stage는 `409 http.source_not_allowed`다.
8. `422` / `503` 분류는 recording이 돌려준 실패 종류로만 정한다. HTTP 층이 메시지 · 파일 내용으로 추론하지 않는다.
9. frames · assets는 `case_id`에 속한 ref에만 bytes를 준다. 다른 case의 ref는 존재 여부와 무관하게 `404 http.not_found`다.
10. 응답 어디에도 `execution_id` · `attempt` · lease · queue 같은 Runtime 내부 필드가 나가지 않는다. job 상태 endpoint는 없다.
11. `/commands`가 `503`을 주면 그 command는 반영되지 않았다(case 저장 · enqueue 전체 rollback).
12. `http.*` 오류의 `message_key`는 `error.code`와 같다.

## 8. OpenAPI와의 관계

이 문서가 손으로 쓴 SoT다. 순서는 `HTTP API Contract → 구현 → FastAPI가 만든 OpenAPI`이며, 생성된 OpenAPI는 이 문서를 구현한 산출물이다. OpenAPI JSON · YAML을 별도 authority로 두지 않는다. 둘이 다르면 이 문서가 맞고 구현을 고친다.

## 9. 구현 선행 조건 · 후속 결정

이 절의 어느 항목도 Final을 막지 않는다(§10). v0 §9에 있던 「source 연결 거부 규칙」 · 「등록 실패 422/503 기준」 · 「빈 case 값」 · 「`http.*` `message_key`」는 리뷰에서 결정돼 본문(§3.3 · §3.4 · §5.1 · §5.2)으로 옮겼다.

### 9.1 구현 선행 조건

계약의 방향은 정해졌고, 해당 capability가 아직 구현되지 않았다. HTTP route 구현 전에 각 Owner가 맞춘다. 이 문서의 의미는 바뀌지 않는다.

| 항목 | Owner | 이 문서 위치 |
| --- | --- | --- |
| 빈 case 생성 `create_case()` · 원본 연결 `record_source_registered()`(`INTAKE` 전용, `file_count` 규칙) — [#270](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/270)(8-12 · 8-17) | case | §5.1 · §5.2 |
| command 응답 `case_view.running_jobs`에 이번 발주를 `PENDING`으로 싣기(8-11) · append 목록을 응답 밖으로 돌려주기(8-7, [#268](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/pull/268)) | case | §5.3 · §7-2 |
| 분석 시작 · 중단 command `kind`와 payload — 분석 시작은 case-command §11 초안(#260), 중단은 #245 결정대로 추가 | case(case-command) | §5.3은 `kind`와 무관하게 동작. 중단은 발주가 없으므로 `200` |
| 사용자 원본 파일명을 등록에 넘기는 인자 — 현재 `register_local_source(path)`에는 없다 | recording | §5.2 `filename` |
| 등록 실패 taxonomy 세분화 — ffprobe 비정상 종료를 결정적 거부(`UNSUPPORTED_MEDIA`)와 일시 실패(`TEMPORARY_FAILURE`)로 나눔. 보완 전에는 손상 · 미지원 입력도 `503` | recording | §5.2 분류 |
| ref → case 소유 조회 capability(FrameRef → MediaStream → SourceAsset → case 연결 · DerivedAsset → case 연결) | recording | §3.5 |
| DerivedAsset bytes · 형식(`Content-Type`) open/read capability(DerivedAsset 계약에 형식 필드 없음) · FrameRef 이미지 형식 제공 | recording | §5.5 · §5.6 header |
| §5.5 배치(composition root가 `read_frame` 호출, recording 승인)에 맞춰 같은 문구 정합 — `contract-source-asset-media-stream.md` §7 · §9-6 · CaseView 계약 B절 §5 · §13 | recording · case | §5.5 |
| `contract` · `contract_version` 키를 CaseView 계약 B절 §5 schema에 등재(case 결정, 구현은 이미 싣는다) | case | 전달 그대로 — HTTP는 키를 더하거나 빼지 않는다 |
| `case.command.*`의 `message_key` 목록 | case · web(case-command §9) | §3.3 — 이 문서는 정하지 않는다 |

### 9.2 후속 결정 — 이 버전 범위 밖

| 항목 | Owner | 이 문서에 미치는 영향 |
| --- | --- | --- |
| `manifest_summary.failed_file_count`가 무엇을 세는지 · 거부된 upload 이력을 영속할지 — 손상 영상을 모두 `201 + UNAVAILABLE`로 등록하는 안은 철회됐다(PR #265 recording · case 답변). 그 전까지 case는 0으로 둔다 | case · recording · web | 없음 — web은 MVP에서 이 값을 쓰지 않는다(§5.2). 새로고침 뒤 실패 목록 복원이 필요해지면 연다 |
| purge 뒤 ref 의미(tombstone 유무) — 정해지면 `410` 재검토 | RD-10 · recording | §3.4 · §5.6 |

**Reopen trigger:** 인증 방식(A2)이 경로나 브라우저 직접 열기 전제를 바꿈 · 외부 공개 · reverse proxy(RD-14)가 body 한도나 buffering을 바꿈 · upload 실패 · 디스크 압박이 관찰돼 #247 H-5를 바꿈 · 동시 upload나 응답 유실로 중복 SourceAsset이 실제 문제가 됨(upload idempotency 검토).

## 10. Final 승격 조건

1. web(신유민) Consumer review — §6 흐름을 이 문서만으로 구현할 수 있는가.
2. case(유소연) boundary review — §5.1 · §5.3 · §5.4가 command · CaseView 의미를 바꾸지 않는가, 200 / 202 기준이 dispatch 의미와 맞는가.
3. recording(정철원) boundary review — §5.2 응답 시점 · §5.5 FrameRef dereference · §5.6 asset 다운로드 · §3.5 소유 경계.
4. 리뷰 반영 뒤 Status를 `Final — Accepted`로, Contract Version을 `http-api/v1`로 올리고 짝 ADR §5에 review 결과를 남긴 뒤 Accepted로 바꾼다.

**충족 (2026-10-05).** 1 ~ 3의 리뷰가 PR #265에서 끝났고(web · case는 「Final을 막는 항목 없음」, recording은 §5.2 응답 시점 · §5.5 · §3.5 동의 · §5.6 방향 동의에 구현 선행 조건 유지 요청) 결론을 이 판본에 반영했다(4). 리뷰별 결과는 짝 ADR §5다. 남은 것은 §9의 구현 선행 조건 · 후속 결정뿐이다.
