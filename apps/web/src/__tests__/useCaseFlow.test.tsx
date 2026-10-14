// @vitest-environment jsdom
//
// 훅은 store를 구독하고, 화면이 붙어 있는 동안만 진행을 갱신한다.

import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Api } from '../api/client'
import type { CaseView } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { useCaseFlow } from '../state/useCaseFlow'

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('상태를 구독하고, 화면이 떠나면 진행 갱신을 멈춘다', async () => {
  const running = [{ job_id: 'j1', kind: 'COARSE_SEARCH', label_key: 'job.generic_processing', status: 'RUNNING' }]
  const view = { ...SNAPSHOTS[0].view, case_rev: 2, running_jobs: running } as CaseView
  const getView = vi.fn().mockResolvedValue({ ok: true, status: 200, data: view })
  const api = { getView, frameUrl: () => '', assetUrl: () => '' } as unknown as Api

  const { result, unmount } = renderHook(() => useCaseFlow(api, { pollMs: 1000 }))
  expect(result.current.state.view).toBeNull()

  await act(async () => {
    await result.current.resume('c1')
  })
  expect(result.current.state.view?.case_rev).toBe(2)

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000)
  })
  expect(getView).toHaveBeenCalledTimes(2)

  unmount()
  await vi.advanceTimersByTimeAsync(10_000)
  expect(getView).toHaveBeenCalledTimes(2)
})
