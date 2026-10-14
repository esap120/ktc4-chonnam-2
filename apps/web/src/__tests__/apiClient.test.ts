// HTTP API 클라이언트 — `contract-http-api.md`(http-api/v1)의 요청 모양과 status 처리를 고정한다.

import { describe, expect, it } from 'vitest'
import { INVALID_RESPONSE, NETWORK_ERROR, createApi } from '../api/client'
import { SNAPSHOTS } from '../contracts/fixtures'

const VIEW = SNAPSHOTS[0].view

interface Seen {
  url: string
  init?: RequestInit
}

/** 응답 하나를 돌려주는 가짜 fetch. 받은 요청은 `seen`에 쌓는다. */
function fake(status: number, body: unknown, seen: Seen[] = []): typeof fetch {
  return (async (url: string, init?: RequestInit) => {
    seen.push({ url, init })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
}

const envelope = (code: string, case_view: unknown = null) => ({
  ok: false,
  error: { code, message_key: code },
  case_view,
})

describe('요청 모양', () => {
  it('POST /cases는 body 없이 보내고 201 body를 그대로 준다(§5.1)', async () => {
    const seen: Seen[] = []
    const api = createApi({ fetch: fake(201, { case_id: 'case_a', case_view: VIEW }, seen) })
    const res = await api.createCase()
    expect(seen[0].url).toBe('/cases')
    expect(seen[0].init?.method).toBe('POST')
    expect(seen[0].init?.body).toBeUndefined()
    expect(res).toEqual({ ok: true, status: 201, data: { case_id: 'case_a', case_view: VIEW } })
  })

  it('baseUrl이 있으면 모든 경로 앞에 붙는다(§3.1)', async () => {
    const seen: Seen[] = []
    const api = createApi({ baseUrl: 'http://api.test', fetch: fake(200, VIEW, seen) })
    await api.createCase()
    await api.getView('case_a')
    expect(seen.map((s) => s.url)).toEqual(['http://api.test/cases', 'http://api.test/cases/case_a/view'])
  })

  it('업로드는 file part 하나만 보내고 Content-Type은 브라우저에 맡긴다(§5.2)', async () => {
    const seen: Seen[] = []
    const api = createApi({ fetch: fake(201, { case_id: 'case_a', source_asset_ref: 'sa_1', case_view: VIEW }, seen) })
    const file = new File(['x'], '20260824_180000_EVT_1.mp4', { type: 'video/mp4' })
    const res = await api.uploadSource('case_a', file)
    const form = seen[0].init!.body as FormData
    expect(seen[0].url).toBe('/cases/case_a/sources')
    expect([...form.keys()]).toEqual(['file'])
    expect((form.get('file') as File).name).toBe('20260824_180000_EVT_1.mp4')
    expect(seen[0].init?.headers).toBeUndefined()
    expect(res.ok && res.data.source_asset_ref).toBe('sa_1')
  })

  it('command는 case-command 요청 그대로 보내고, 성공이면 case_view만 꺼내 준다(§5.3)', async () => {
    const seen: Seen[] = []
    const api = createApi({ fetch: fake(202, { ok: true, error: null, case_view: VIEW }, seen) })
    const res = await api.sendCommand('case_a', 4, { kind: 'RECORD_SITUATION_RESPONSE', payload: { value: 'CONFIRMED' } })
    expect(seen[0].url).toBe('/cases/case_a/commands')
    expect(seen[0].init?.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(seen[0].init!.body as string)).toEqual({
      case_id: 'case_a',
      expected_case_rev: 4,
      kind: 'RECORD_SITUATION_RESPONSE',
      payload: { value: 'CONFIRMED' },
    })
    expect(res).toEqual({ ok: true, status: 202, data: VIEW })
  })

  it('GET /view는 감싸지 않은 CaseView를 그대로 주고 브라우저 cache를 타지 않는다(§5.4)', async () => {
    const seen: Seen[] = []
    const api = createApi({ fetch: fake(200, VIEW, seen) })
    const res = await api.getView('case_a')
    expect(seen[0].url).toBe('/cases/case_a/view')
    expect(seen[0].init?.method).toBeUndefined()
    expect(seen[0].init?.cache).toBe('no-store')
    expect(res).toEqual({ ok: true, status: 200, data: VIEW })
  })

  it('id는 percent-encoding만 하고 해석하지 않는다(§3.1)', () => {
    const api = createApi()
    expect(api.frameUrl('case_a', 'fr/x y')).toBe('/cases/case_a/frames/fr%2Fx%20y')
    expect(api.assetUrl('case a', 'da_1')).toBe('/cases/case%20a/assets/da_1')
  })
})

describe('실패 응답', () => {
  it('command 409(stale)는 case가 실은 case_view를 같이 준다 — 다시 읽지 않고 그 값으로 그린다(§3.2)', async () => {
    const api = createApi({ fetch: fake(409, envelope('case.command.stale_revision', VIEW)) })
    const res = await api.sendCommand('case_a', 3, { kind: 'MARK_REVIEWED', payload: {} })
    expect(res).toEqual({
      ok: false,
      status: 409,
      error: { code: 'case.command.stale_revision', message_key: 'case.command.stale_revision' },
      caseView: VIEW,
    })
  })

  it('업로드 422는 파일과 짝지을 수 있게 status · code를 그대로 준다(§5.2)', async () => {
    const api = createApi({ fetch: fake(422, envelope('http.source_rejected')) })
    const res = await api.uploadSource('case_a', new File(['x'], 'a.mp4'))
    expect(res).toMatchObject({ ok: false, status: 422, error: { code: 'http.source_rejected' }, caseView: null })
  })

  it.each([
    [404, 'http.not_found'],
    [500, 'http.internal_error'],
    [503, 'http.dependency_unavailable'],
  ])('%i는 envelope의 code를 덮지 않는다(§3.4)', async (status, code) => {
    const api = createApi({ fetch: fake(status, envelope(code)) })
    expect(await api.getView('case_a')).toMatchObject({ ok: false, status, error: { code }, caseView: null })
  })

  it('응답이 없으면 status 0 · web.network_error다 — 서버 code와 섞이지 않는다(§7-5)', async () => {
    const api = createApi({
      fetch: (async () => {
        throw new TypeError('Failed to fetch')
      }) as typeof fetch,
    })
    expect(await api.getView('case_a')).toEqual({
      ok: false,
      status: 0,
      error: { code: NETWORK_ERROR, message_key: NETWORK_ERROR },
      caseView: null,
    })
  })

  it('프록시가 낸 HTML 같은 envelope이 아닌 응답은 status를 남기고 web.invalid_response다', async () => {
    const api = createApi({ fetch: (async () => new Response('<h1>Bad Gateway</h1>', { status: 502 })) as typeof fetch })
    expect(await api.getView('case_a')).toEqual({
      ok: false,
      status: 502,
      error: { code: INVALID_RESPONSE, message_key: INVALID_RESPONSE },
      caseView: null,
    })
  })

  it('시간 제한을 넘기면 응답 없음(status 0)이다 — 반영 여부를 모른다(§3.4)', async () => {
    const hang = ((_url: string, init?: RequestInit) =>
      new Promise((_resolve, reject) =>
        init?.signal?.addEventListener('abort', () => reject(new DOMException('timeout', 'TimeoutError'))),
      )) as typeof fetch
    const res = await createApi({ timeoutMs: 5, fetch: hang }).getView('case_a')
    expect(res).toMatchObject({ ok: false, status: 0, error: { code: NETWORK_ERROR } })
  })

  it('업로드에는 시간 제한을 두지 않고 JSON 요청에만 둔다', async () => {
    const seen: Seen[] = []
    const api = createApi({ fetch: fake(200, VIEW, seen) })
    await api.uploadSource('case_a', new File(['x'], 'a.mp4'))
    await api.getView('case_a')
    expect(seen[0].init?.signal).toBeUndefined()
    expect(seen[1].init?.signal).toBeInstanceOf(AbortSignal)
  })

  it('envelope이 아닌 JSON 오류(프레임워크 기본 `detail`)도 서버 code로 믿지 않는다(§3.3)', async () => {
    const api = createApi({ fetch: fake(422, { detail: [{ msg: 'field required' }] }) })
    expect(await api.getView('case_a')).toMatchObject({ ok: false, status: 422, error: { code: INVALID_RESPONSE } })
  })
})
