// @vitest-environment jsdom
//
// `?api` 흐름 — 화면은 CaseView로 고르고, 버튼은 command로 이어진다(contract-case-command · contract-http-api §6).
// 서버가 없으므로 Api를 가짜로 끼운다.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Api, ApiResult } from '../api/client'
import type { CaseView, Notice } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { ApiFlow } from '../screens/ApiFlow'

afterEach(cleanup)
beforeEach(() => history.replaceState(null, '', '/?api'))

const BASE = SNAPSHOTS[0].view
const JOBS = [
  { job_id: 'j1', kind: 'COARSE_SEARCH', label_key: 'job.generic_processing', status: 'RUNNING' },
] as CaseView['running_jobs']
const notice = (code: string, actions: string[]): Notice => ({
  code,
  severity: 'INFO',
  blocking: false,
  message_key: code.replace('case.', 'notice.'),
  actions,
})
const view = (patch: Partial<CaseView>): CaseView => ({
  ...BASE,
  case_rev: 1,
  stage: 'INTAKE',
  running_jobs: [],
  notices: [],
  manifest_summary: { ...BASE.manifest_summary, file_count: 0, ok_file_count: 0 },
  ...patch,
})
const ok = <T,>(data: T, status = 200): ApiResult<T> => ({ ok: true, status, data })
const NETWORK_DOWN: ApiResult<never> = { ok: false, status: 0, error: { code: 'web.network_error', message_key: 'web.network_error' }, caseView: null }

const SEARCHING = view({ case_rev: 2, stage: 'SEARCHING', running_jobs: JOBS, manifest_summary: { ...BASE.manifest_summary, file_count: 1, ok_file_count: 1 } })
const STOPPED = view({
  case_rev: 3,
  stage: 'SEARCHING',
  notices: [notice('case.analysis_stopped', ['RETRY_SEARCH'])],
})
const AWAITING = SNAPSHOTS.map((s) => s.view).find((v) => v.notices.some((n) => n.code === 'case.situation_response_pending'))!

function setup(views: { get?: CaseView } = {}) {
  const m = {
    createCase: vi.fn().mockResolvedValue(ok({ case_id: 'c1', case_view: view({}) }, 201)),
    uploadSource: vi
      .fn()
      .mockResolvedValue(
        ok({ case_id: 'c1', source_asset_ref: 'sa', case_view: view({ manifest_summary: { ...BASE.manifest_summary, file_count: 1, ok_file_count: 1 } }) }, 201),
      ),
    sendCommand: vi.fn(),
    getView: vi.fn().mockResolvedValue(ok(views.get ?? view({}))),
  }
  const api = { ...m, frameUrl: () => '', assetUrl: () => '' } as unknown as Api
  return { m, api }
}

it('영상을 고르면 올라가고, [영상에서 찾아보기]에서 상황 설명과 함께 분석을 시작한다', async () => {
  const { m, api } = setup()
  m.sendCommand.mockResolvedValue(ok(SEARCHING, 202))
  const { container, getByRole, getByText, findByText } = render(<ApiFlow api={api} />)

  fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [new File(['x'], 'a.mp4')] } })
  await findByText('올리기 완료')
  expect(m.createCase).toHaveBeenCalledOnce()
  expect(m.uploadSource).toHaveBeenCalledWith('c1', expect.objectContaining({ name: 'a.mp4' }))
  expect(m.sendCommand).not.toHaveBeenCalled() // 고르는 것만으로 분석이 시작되지 않는다

  fireEvent.change(getByRole('textbox'), { target: { value: '흰 SUV가 끼어들었어요' } })
  fireEvent.click(getByText('영상에서 찾아보기'))
  await findByText('분석 중단')
  expect(m.sendCommand).toHaveBeenCalledWith('c1', 1, { kind: 'START_ANALYSIS', payload: { description: '흰 SUV가 끼어들었어요' } })
  expect(location.search).toContain('case=c1') // 새로고침해도 이어진다
})

it('올리는 중에 고른 파일은 받지 않고 목록에도 올리지 않는다', async () => {
  const { m, api } = setup()
  let finish!: (r: unknown) => void
  m.uploadSource.mockImplementationOnce(() => new Promise((r) => (finish = r)))
  const { container, findByText, queryByText } = render(<ApiFlow api={api} />)
  const input = container.querySelector('input[type=file]')!

  fireEvent.change(input, { target: { files: [new File(['x'], 'a.mp4')] } })
  await findByText('올리는 중')
  fireEvent.change(input, { target: { files: [new File(['x'], 'b.mp4')] } })
  finish(ok({ case_id: 'c1', source_asset_ref: 'sa', case_view: view({ manifest_summary: { ...BASE.manifest_summary, file_count: 1, ok_file_count: 1 } }) }, 201))
  await findByText('올리기 완료')

  expect(m.uploadSource).toHaveBeenCalledOnce()
  expect(queryByText(/b\.mp4/)).toBeNull()
})

it('시작 전에 이어받은 case는 서버에 있는 영상을 개수로 보이고 바로 시작할 수 있다 — 다시 올리지 않는다', async () => {
  const intake = view({ case_rev: 2, manifest_summary: { ...BASE.manifest_summary, file_count: 1, ok_file_count: 1 } })
  const { m, api } = setup({ get: intake })
  m.sendCommand.mockResolvedValue(ok(SEARCHING, 202))
  const { findByText, getByText } = render(<ApiFlow api={api} caseId="c1" />)
  await findByText('이미 올린 영상 1개')
  expect(getByText('올리기 완료')).toBeTruthy()
  fireEvent.click(getByText('영상에서 찾아보기'))
  await findByText('분석 중단')
  expect(m.uploadSource).not.toHaveBeenCalled()
  expect(m.sendCommand).toHaveBeenCalledWith('c1', 2, { kind: 'START_ANALYSIS', payload: { description: '' } })
})

it('[분석 중단]은 STOP_ANALYSIS를 보내고, 중단 화면에서 [다시 찾기]는 RETRY_SEARCH 알림 동작이다', async () => {
  const { m, api } = setup({ get: SEARCHING })
  m.sendCommand.mockResolvedValue(ok(STOPPED))
  const { findByText, getByText } = render(<ApiFlow api={api} caseId="c1" />)

  fireEvent.click(await findByText('분석 중단'))
  await findByText('분석을 중단했어요.')
  expect(m.sendCommand).toHaveBeenCalledWith('c1', 2, { kind: 'STOP_ANALYSIS', payload: {} })

  m.sendCommand.mockResolvedValue(ok({ ...SEARCHING, case_rev: 4 })) // 다시 찾으면 rev가 오른다
  fireEvent.click(getByText('다시 찾기'))
  await findByText('분석 중단')
  expect(m.sendCommand).toHaveBeenLastCalledWith('c1', 3, {
    kind: 'RUN_NOTICE_ACTION',
    payload: { notice_code: 'case.analysis_stopped', action: 'RETRY_SEARCH' },
  })
})

it('찾는 중이 아닐 때(SEARCHING이 아닐 때)는 중단 버튼을 두지 않는다', async () => {
  const { api } = setup({ get: view({ case_rev: 5, stage: 'CANDIDATE_REVIEW', running_jobs: JOBS, candidates: BASE.candidates }) })
  const { findByText, queryByText } = render(<ApiFlow api={api} caseId="c1" />)
  await findByText(/신고자료를 준비하고 있어요|사건을 찾고 있어요/)
  expect(queryByText('분석 중단')).toBeNull()
})

it('신고 상황 응답은 RECORD_SITUATION_RESPONSE로 보낸다', async () => {
  const { m, api } = setup({ get: AWAITING })
  m.sendCommand.mockResolvedValue(ok({ ...AWAITING, case_rev: AWAITING.case_rev + 1 }))
  const { findByText } = render(<ApiFlow api={api} caseId="c1" />)
  fireEvent.click(await findByText('맞아요'))
  await waitFor(() => expect(m.sendCommand).toHaveBeenCalled())
  expect(m.sendCommand).toHaveBeenCalledWith('c1', AWAITING.case_rev, { kind: 'RECORD_SITUATION_RESPONSE', payload: { value: 'CONFIRMED' } })
})

it('요청이 실패하면 화면은 그대로 두고 알림만 띄운다', async () => {
  const { m, api } = setup({ get: SEARCHING })
  m.sendCommand.mockResolvedValue(NETWORK_DOWN)
  m.getView.mockResolvedValue(ok(SEARCHING)) // 반영 여부를 모르면 먼저 읽는다
  const { findByText } = render(<ApiFlow api={api} caseId="c1" />)
  fireEvent.click(await findByText('분석 중단'))
  await findByText('서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.')
  expect(await findByText('분석 중단')).toBeTruthy()
})

it('command가 없는 알림 버튼(직접 입력류)은 보내지 않고 안내한다', async () => {
  const stopped = view({ case_rev: 3, stage: 'SEARCHING', notices: [notice('case.analysis_stopped', ['MANUAL_PLATE_INPUT'])] })
  const { m, api } = setup({ get: stopped })
  const { findByText } = render(<ApiFlow api={api} caseId="c1" />)
  fireEvent.click(await findByText('번호판 직접 입력'))
  await findByText('이 동작은 아직 연결되지 않았어요.')
  expect(m.sendCommand).not.toHaveBeenCalled()
})
