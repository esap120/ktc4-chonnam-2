import { useEffect, useState, useSyncExternalStore } from 'react'
import type { Api } from '../api/client'
import { createCaseFlow, type FlowOptions } from './caseFlow'

/**
 * 화면이 붙어 있는 동안 진행을 갱신하고, 상태 변화를 구독한다. 상태는 CaseView 1건과 업로드 결과뿐이다
 * (web-stack.md 확정 4). 화면은 `state.view`를 `selectScreen`에 넘겨 고른다.
 * `api` · `options`는 처음 한 번만 쓴다 — 바꾸려면 훅을 새로 마운트한다.
 */
export function useCaseFlow(api: Api, options?: FlowOptions) {
  const [flow] = useState(() => createCaseFlow(api, options))
  const state = useSyncExternalStore(flow.subscribe, flow.getState)
  // connect는 끊는 함수를 돌려준다 — StrictMode가 붙였다 떼었다 다시 붙여도 갱신이 이어진다.
  useEffect(() => flow.connect(), [flow])
  return { state, addFiles: flow.addFiles, send: flow.send, resume: flow.resume }
}
