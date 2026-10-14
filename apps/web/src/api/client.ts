// HTTP API 클라이언트 — `contract-http-api.md`(http-api/v1)를 그대로 옮긴다.
//
// web은 domain 의미를 다시 계산하지 않는다(계약 §1). 이 파일은 요청을 보내고 응답을 status와
// body 그대로 돌려줄 뿐, 재시도 · polling · 화면 판단을 하지 않는다 — 그건 부르는 쪽 몫이다.
// 재시도 규칙(계약 §3.4): 503은 반영되지 않았으니 다시 보내도 되고, 500 · 응답 없음은 반영 여부를
// 모르니 POST를 다시 보내기 전에 GET /view로 확인한다.

import type { CaseView } from '../contracts/caseView'

/** §3.3 envelope의 `error`. `http.*`는 HTTP 층, `case.command.*`는 case가 만든 값이다. */
export interface ApiError {
  code: string
  message_key: string
}

/** 서버가 만든 code와 섞이지 않게 client가 만든 오류는 `web.`로 시작한다(계약 §7-5). */
export const NETWORK_ERROR = 'web.network_error'
export const INVALID_RESPONSE = 'web.invalid_response'

/**
 * 성공이면 body 그대로, 실패면 status · error · (case가 실어 준) case_view.
 * `/commands`의 409(stale)는 case_view가 있으니 부르는 쪽이 다시 읽지 않고 그 값으로 그린다(§3.2).
 */
export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: ApiError; caseView: CaseView | null }

export interface CaseCreated {
  case_id: string
  case_view: CaseView
}

export interface SourceRegistered {
  case_id: string
  source_asset_ref: string
  case_view: CaseView
}

/** case-command §5 — kind별 payload. */
export type Command =
  | { kind: 'START_ANALYSIS'; payload: { description: string } }
  | { kind: 'STOP_ANALYSIS'; payload: Record<string, never> }
  | { kind: 'SELECT_OTHER_CANDIDATE'; payload: { candidate_id: string } }
  | { kind: 'RECORD_SITUATION_RESPONSE'; payload: { value: 'CONFIRMED' | 'USER_UNSURE' } }
  | { kind: 'MARK_REVIEWED'; payload: Record<string, never> }
  | {
      kind: 'RUN_NOTICE_ACTION'
      payload: {
        notice_code: string
        action: 'GENERATE_REPORT_VIDEO' | 'RETRY_PLATE_READ' | 'RETRY_SEARCH' | 'GENERATE_PLATE_IMAGE'
      }
    }

export interface ApiOptions {
  /** 배포가 정한다(계약 §3.1). 같은 origin이면 비워 둔다. */
  baseUrl?: string
  fetch?: typeof fetch
  /**
   * JSON 요청(view · command · 생성)의 시간 제한. 넘으면 「응답 없음」이라 반영 여부를 모른다 —
   * 부르는 쪽이 GET /view로 확인한다(계약 §3.4). 숫자는 web 구현값이다(§4).
   */
  timeoutMs?: number
}

export function createApi(options: ApiOptions = {}) {
  const base = options.baseUrl ?? ''
  const timeoutMs = options.timeoutMs ?? 15_000
  const doFetch = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  // id는 서버가 발급한 opaque 문자열이다 — percent-encoding만 하고 해석하지 않는다(§3.1).
  const caseUrl = (caseId: string) => `${base}/cases/${encodeURIComponent(caseId)}`

  const fail = (status: number, code: string): ApiResult<never> => ({
    ok: false,
    status,
    error: { code, message_key: code },
    caseView: null,
  })

  async function call<T>(url: string, init?: RequestInit, withTimeout = true): Promise<ApiResult<T>> {
    let res: Response
    try {
      res = await doFetch(url, { ...init, signal: withTimeout ? AbortSignal.timeout(timeoutMs) : undefined })
    } catch {
      return fail(0, NETWORK_ERROR)
    }
    let body: any
    try {
      body = await res.json()
    } catch {
      // 프록시 · 게이트웨이가 낸 HTML 등 — 계약의 envelope이 아니다.
      return fail(res.status, INVALID_RESPONSE)
    }
    if (res.ok) return { ok: true, status: res.status, data: body as T }
    // envelope이 아닌 JSON(예: 프레임워크 기본 오류)은 서버 code로 믿지 않는다.
    if (!body?.error) return fail(res.status, INVALID_RESPONSE)
    return { ok: false, status: res.status, error: body.error, caseView: body.case_view ?? null }
  }

  return {
    /** §5.1 — body 없음. `case_id`는 서버가 발급한다. */
    createCase: () => call<CaseCreated>(`${base}/cases`, { method: 'POST' }),

    /**
     * §5.2 — 1 request = 1 file. `file` part 하나만 보내고 Content-Type(boundary)은 브라우저에 맡긴다.
     * 영상은 오래 걸릴 수 있어 시간 제한을 두지 않는다(한도는 서버 · 프록시가 정한다).
     */
    uploadSource(caseId: string, file: File) {
      const form = new FormData()
      form.append('file', file)
      return call<SourceRegistered>(`${caseUrl(caseId)}/sources`, { method: 'POST', body: form }, false)
    },

    /**
     * §5.3 — case-command 요청 그대로. 성공 body는 case-command 응답이라 `case_view`만 꺼내 준다.
     * status(200 / 202)는 「발주했는가」일 뿐이고 polling 여부는 `running_jobs`가 정한다(§5.4).
     */
    async sendCommand(caseId: string, expectedCaseRev: number, command: Command): Promise<ApiResult<CaseView>> {
      const res = await call<{ case_view: CaseView }>(`${caseUrl(caseId)}/commands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId, expected_case_rev: expectedCaseRev, ...command }),
      })
      return res.ok ? { ok: true, status: res.status, data: res.data.case_view } : res
    },

    /**
     * §5.4 — body가 CaseView 그대로다(감싸지 않는다). 폴링 값이라 브라우저 cache를 타면 낡은
     * `running_jobs`가 와서 진행이 멈춘 것처럼 보인다 — 계약이 Cache-Control을 정하지 않으니 여기서 막는다.
     */
    getView: (caseId: string) => call<CaseView>(`${caseUrl(caseId)}/view`, { cache: 'no-store' }),

    /** §5.5 · §5.6 — `<img src>` · 다운로드 링크로 직접 연다(추가 header 없음, §3.6). */
    frameUrl: (caseId: string, frameRef: string) => `${caseUrl(caseId)}/frames/${encodeURIComponent(frameRef)}`,
    assetUrl: (caseId: string, assetRef: string) => `${caseUrl(caseId)}/assets/${encodeURIComponent(assetRef)}`,
  }
}

export type Api = ReturnType<typeof createApi>
