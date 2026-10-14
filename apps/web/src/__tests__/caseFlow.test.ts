// 사용자 흐름 — 영상 올리기 → 분석 시작 → 진행 갱신 → command (`contract-http-api.md` §3.4 · §5 · §6).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api, ApiResult } from '../api/client'
import type { CaseView } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { createCaseFlow, type FlowOptions } from '../state/caseFlow'

const BASE = SNAPSHOTS[0].view
const JOBS = [
  { job_id: 'j1', kind: 'COARSE_SEARCH', label_key: 'job.generic_processing', status: 'RUNNING' },
] as CaseView['running_jobs']

const manifest = (file_count: number, ok_file_count = file_count) => ({ ...BASE.manifest_summary, file_count, ok_file_count })
// 기본은 막 만든 case — 올라간 영상이 없다(fixture의 업로드 수를 가져오지 않는다).
const view = (patch: Partial<CaseView> = {}): CaseView => ({
  ...BASE,
  case_rev: 1,
  running_jobs: [],
  manifest_summary: manifest(0),
  ...patch,
})
const ok = <T>(data: T, status = 200): ApiResult<T> => ({ ok: true, status, data })
const bad = (status: number, code = 'e', caseView: CaseView | null = null): ApiResult<never> => ({
  ok: false,
  status,
  error: { code, message_key: code },
  caseView,
})
const file = (name: string) => new File(['x'], name)
const NO_RESPONSE = bad(0, 'web.network_error')

function setup(options?: FlowOptions) {
  const m = { createCase: vi.fn(), uploadSource: vi.fn(), sendCommand: vi.fn(), getView: vi.fn() }
  const api = { ...m, frameUrl: () => '', assetUrl: () => '' } as unknown as Api
  return { m, flow: createCaseFlow(api, options) }
}

/** 시작 · 업로드 · command가 성공하는 기본 응답. 필요한 것만 덮어쓴다. */
function created(m: ReturnType<typeof setup>['m'], caseView = view()) {
  m.createCase.mockResolvedValue(ok({ case_id: 'c1', case_view: caseView }, 201))
}
const uploaded = (count: number, okCount = count) =>
  ok({ case_id: 'c1', source_asset_ref: 'sa', case_view: view({ manifest_summary: manifest(count, okCount) }) }, 201)

describe('분석 시작', () => {
  it('영상을 하나씩 순서대로 올리고 분석을 시작한다(§5.2 · §6)', async () => {
    const { m, flow } = setup()
    created(m)
    let finishFirst!: (r: unknown) => void
    m.uploadSource.mockImplementationOnce(() => new Promise((r) => (finishFirst = r))).mockResolvedValueOnce(uploaded(2))
    const started = view({ case_rev: 2, running_jobs: JOBS, manifest_summary: manifest(2) })
    m.sendCommand.mockResolvedValue(ok(started, 202))

    const done = flow.start([file('a.mp4'), file('b.mp4')], '흰 SUV')
    await vi.waitFor(() => expect(m.uploadSource).toHaveBeenCalledTimes(1))
    expect(m.uploadSource).toHaveBeenLastCalledWith('c1', expect.objectContaining({ name: 'a.mp4' })) // 둘째는 아직
    finishFirst(uploaded(1))
    await done

    expect(m.uploadSource.mock.calls.map((c) => c[1].name)).toEqual(['a.mp4', 'b.mp4'])
    expect(m.sendCommand).toHaveBeenCalledWith('c1', 1, { kind: 'START_ANALYSIS', payload: { description: '흰 SUV' } })
    expect(flow.getState()).toMatchObject({ caseId: 'c1', view: started, busy: false, error: null })
    expect(flow.getState().uploads.map((u) => u.status)).toEqual(['DONE', 'DONE'])
  })

  it('실패한 파일은 표시하고 나머지로 계속한다(core-user-flow §23)', async () => {
    const { m, flow } = setup()
    created(m)
    m.uploadSource.mockResolvedValueOnce(bad(422, 'http.source_rejected')).mockResolvedValueOnce(uploaded(1))
    m.sendCommand.mockResolvedValue(ok(view({ case_rev: 2 })))
    await flow.start([file('bad.txt'), file('b.mp4')], '')
    expect(flow.getState().uploads.map((u) => [u.status, u.error])).toEqual([
      ['FAILED', 'http.source_rejected'],
      ['DONE', null],
    ])
    expect(m.sendCommand).toHaveBeenCalledOnce()
  })

  it('올라간 영상이 하나도 없으면 시작을 보내지 않는다', async () => {
    const { m, flow } = setup()
    created(m)
    m.uploadSource.mockResolvedValue(bad(422, 'http.source_rejected'))
    await flow.start([file('bad.txt')], '')
    expect(m.sendCommand).not.toHaveBeenCalled()
    expect(flow.getState()).toMatchObject({ busy: false, uploads: [{ status: 'FAILED' }] })
  })

  it('시작하는 동안 다시 눌러도 case는 한 번만 만든다', async () => {
    const { m, flow } = setup()
    created(m)
    m.uploadSource.mockResolvedValue(uploaded(1))
    m.sendCommand.mockResolvedValue(ok(view({ case_rev: 2 })))
    await Promise.all([flow.start([file('a.mp4')], ''), flow.start([file('a.mp4')], '')])
    expect(m.createCase).toHaveBeenCalledOnce()
  })

  it('case를 만들지 못하면 오류만 남기고 멈춘다', async () => {
    const { m, flow } = setup()
    m.createCase.mockResolvedValue(bad(503, 'http.dependency_unavailable'))
    await flow.start([file('a.mp4')], '')
    expect(m.uploadSource).not.toHaveBeenCalled()
    expect(flow.getState()).toMatchObject({ caseId: null, busy: false, uploads: [], error: { code: 'http.dependency_unavailable' } })
  })

  it.each([
    [1, 'DONE', null],
    [0, 'FAILED', 'web.network_error'],
  ])('응답 없는 업로드는 file_count로 확인한다 — 다시 보내지 않는다(file_count %i → %s, §5.2)', async (count, status, error) => {
    const { m, flow } = setup()
    created(m)
    m.uploadSource.mockResolvedValue(NO_RESPONSE)
    m.getView.mockResolvedValue(ok(view({ manifest_summary: manifest(count) })))
    m.sendCommand.mockResolvedValue(ok(view({ case_rev: 2 })))
    await flow.start([file('a.mp4')], '')
    expect(m.uploadSource).toHaveBeenCalledOnce()
    expect(flow.getState().uploads).toMatchObject([{ status, error }])
  })

  it('503은 반영되지 않았다는 뜻이라 확인 없이 실패로 둔다(§3.4)', async () => {
    const { m, flow } = setup()
    created(m)
    m.uploadSource.mockResolvedValue(bad(503, 'http.dependency_unavailable'))
    await flow.start([file('a.mp4')], '')
    expect(m.getView).not.toHaveBeenCalled()
    expect(flow.getState().uploads).toMatchObject([{ status: 'FAILED', error: 'http.dependency_unavailable' }])
  })
})

describe('진행 갱신', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('running_jobs가 있는 동안 간격마다 읽고, 비면 멈춘다(§5.4)', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    m.getView
      .mockResolvedValueOnce(ok(view({ case_rev: 2, running_jobs: JOBS })))
      .mockResolvedValueOnce(ok(view({ case_rev: 3, running_jobs: JOBS })))
      .mockResolvedValue(ok(view({ case_rev: 4 })))
    const disconnect = flow.connect()
    await flow.resume('c1')
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(m.getView).toHaveBeenCalledTimes(3)
    expect(flow.getState().view?.case_rev).toBe(4)
    disconnect()
  })

  it('일시 장애는 다음 주기에 다시 읽고, case가 없으면(404) 멈춘다', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    m.getView
      .mockResolvedValueOnce(ok(view({ case_rev: 2, running_jobs: JOBS })))
      .mockResolvedValueOnce(bad(503, 'http.dependency_unavailable'))
      .mockResolvedValueOnce(bad(404, 'http.not_found'))
      .mockResolvedValue(ok(view({ case_rev: 9 })))
    const disconnect = flow.connect()
    await flow.resume('c1')
    await vi.advanceTimersByTimeAsync(1000)
    expect(flow.getState().error?.code).toBe('http.dependency_unavailable')
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(m.getView).toHaveBeenCalledTimes(3)
    expect(flow.getState().error?.code).toBe('http.not_found')
    disconnect()
  })

  it('옛 응답(case_rev가 줄어든 값)은 화면을 덮지 않고 갱신은 이어간다', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    m.getView
      .mockResolvedValueOnce(ok(view({ case_rev: 5, running_jobs: JOBS })))
      .mockResolvedValueOnce(ok(view({ case_rev: 3, running_jobs: JOBS })))
      .mockResolvedValue(ok(view({ case_rev: 6 })))
    const disconnect = flow.connect()
    await flow.resume('c1')
    await vi.advanceTimersByTimeAsync(1000)
    expect(flow.getState().view?.case_rev).toBe(5)
    await vi.advanceTimersByTimeAsync(1000)
    expect(flow.getState().view?.case_rev).toBe(6)
    disconnect()
  })

  it('화면이 떠나면(disconnect) 더 읽지 않는다', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    m.getView.mockResolvedValue(ok(view({ case_rev: 2, running_jobs: JOBS })))
    const disconnect = flow.connect()
    await flow.resume('c1')
    disconnect()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(m.getView).toHaveBeenCalledOnce()
  })

  it('command가 나가 있는 동안에는 읽지 않는다 — 그 응답이 더 최신이다', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    m.getView.mockResolvedValue(ok(view({ case_rev: 2, running_jobs: JOBS })))
    let finish!: (r: unknown) => void
    m.sendCommand.mockImplementation(() => new Promise((r) => (finish = r)))
    const disconnect = flow.connect()
    await flow.resume('c1')
    const sending = flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    await vi.advanceTimersByTimeAsync(5000)
    expect(m.getView).toHaveBeenCalledOnce()
    finish(ok(view({ case_rev: 3, running_jobs: JOBS })))
    await sending
    await vi.advanceTimersByTimeAsync(1000) // 끝나면 다시 읽는다
    expect(m.getView).toHaveBeenCalledTimes(2)
    disconnect()
  })

  it('읽기가 나간 뒤 command가 나가면 그 읽기 응답은 버린다 — 낡은 running_jobs로 갱신이 멈추지 않게', async () => {
    const { m, flow } = setup({ pollMs: 1000 })
    const jobs2 = [{ ...JOBS[0], job_id: 'j2' }]
    let stale!: (r: unknown) => void
    m.getView
      .mockResolvedValueOnce(ok(view({ case_rev: 2, running_jobs: JOBS })))
      .mockImplementationOnce(() => new Promise((r) => (stale = r)))
    m.sendCommand.mockResolvedValue(ok(view({ case_rev: 2, running_jobs: jobs2 }), 202))
    const disconnect = flow.connect()
    await flow.resume('c1')
    await vi.advanceTimersByTimeAsync(1000) // 읽기가 나가 있다
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    stale(ok(view({ case_rev: 2, running_jobs: [] }))) // 같은 case_rev의 낡은 값
    await vi.advanceTimersByTimeAsync(0)
    expect(flow.getState().view?.running_jobs).toEqual(jobs2)
    disconnect()
  })
})

describe('이어가기', () => {
  it('case id로 GET /view를 읽어 현재 화면을 되찾는다', async () => {
    const { m, flow } = setup()
    m.getView.mockResolvedValue(ok(view({ case_rev: 7 })))
    await flow.resume('c1')
    expect(m.getView).toHaveBeenCalledWith('c1')
    expect(flow.getState()).toMatchObject({ caseId: 'c1', busy: false, view: { case_rev: 7 } })
  })

  it('없는 case(404)면 오류를 남긴다', async () => {
    const { m, flow } = setup()
    m.getView.mockResolvedValue(bad(404, 'http.not_found'))
    await flow.resume('c1')
    expect(flow.getState()).toMatchObject({ view: null, busy: false, error: { code: 'http.not_found' } })
  })
})

describe('command', () => {
  async function ready(m: ReturnType<typeof setup>['m'], flow: ReturnType<typeof setup>['flow'], rev = 4) {
    m.getView.mockResolvedValueOnce(ok(view({ case_rev: rev })))
    await flow.resume('c1')
  }

  it('화면이 본 case_rev를 expected_case_rev로 보내고, 성공하면 그 화면으로 바꾼다(§5.3)', async () => {
    const { m, flow } = setup()
    await ready(m, flow)
    m.sendCommand.mockResolvedValue(ok(view({ case_rev: 5, user_reviewed: true })))
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    expect(m.sendCommand).toHaveBeenCalledWith('c1', 4, { kind: 'MARK_REVIEWED', payload: {} })
    expect(flow.getState()).toMatchObject({ busy: false, error: null, view: { case_rev: 5, user_reviewed: true } })
  })

  it('409(stale)는 case가 실은 현재 화면으로 바꾼다 — 따로 다시 읽지 않는다(§3.2)', async () => {
    const { m, flow } = setup()
    await ready(m, flow)
    m.sendCommand.mockResolvedValue(bad(409, 'case.command.stale_revision', view({ case_rev: 7 })))
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    expect(m.getView).toHaveBeenCalledTimes(1) // resume 한 번뿐
    expect(flow.getState()).toMatchObject({ view: { case_rev: 7 }, error: { code: 'case.command.stale_revision' } })
  })

  it('반영 여부를 모르면 다시 보내지 않고 먼저 읽는다(§3.4)', async () => {
    const { m, flow } = setup()
    await ready(m, flow)
    m.sendCommand.mockResolvedValue(NO_RESPONSE)
    m.getView.mockResolvedValueOnce(ok(view({ case_rev: 5 })))
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    expect(m.sendCommand).toHaveBeenCalledOnce()
    expect(flow.getState()).toMatchObject({ view: { case_rev: 5 }, busy: false })
  })

  it('503은 반영되지 않았으니 읽지 않고 오류만 남긴다', async () => {
    const { m, flow } = setup()
    await ready(m, flow)
    m.sendCommand.mockResolvedValue(bad(503, 'http.dependency_unavailable'))
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    expect(m.getView).toHaveBeenCalledTimes(1)
    expect(flow.getState()).toMatchObject({ view: { case_rev: 4 }, error: { code: 'http.dependency_unavailable' } })
  })

  it('요청이 나가 있는 동안 같은 버튼을 또 눌러도 command는 한 번만 나간다', async () => {
    const { m, flow } = setup()
    await ready(m, flow)
    let finish!: (r: unknown) => void
    m.sendCommand.mockImplementation(() => new Promise((r) => (finish = r)))
    const first = flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    finish(ok(view({ case_rev: 5 })))
    await first
    expect(m.sendCommand).toHaveBeenCalledOnce()
  })

  it('case가 없으면(아직 시작 전) 아무것도 보내지 않는다', async () => {
    const { m, flow } = setup()
    await flow.send({ kind: 'MARK_REVIEWED', payload: {} })
    expect(m.sendCommand).not.toHaveBeenCalled()
  })
})
