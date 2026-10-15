// 사용자 흐름 — 영상 올리기 → 분석 시작 → 진행 갱신 → command. 계약은 `contract-http-api.md` §6이다.
//
// 진실의 원천은 CaseView 1건이다(web-stack.md 확정 4). 여기에는 화면 판단이 없고, 로컬 상태는
// 계약이 web에 맡긴 것뿐이다 — 파일별 업로드 결과(CaseView에 파일별 목록이 없다, §5.2)와 마지막 오류.
// React와 무관하게 만들어 둔다 — 훅(`useCaseFlow`)은 이 store를 구독만 한다.

import type { Api, ApiError, Command } from '../api/client'
import type { CaseView } from '../contracts/caseView'

export interface UploadItem {
  name: string
  status: 'WAITING' | 'UPLOADING' | 'DONE' | 'FAILED'
  /** 실패한 응답의 `error.code`. 문구는 화면이 code별로 연결한다(§3.3). */
  error: string | null
}

export interface FlowState {
  caseId: string | null
  view: CaseView | null
  uploads: UploadItem[]
  /** 마지막 실패. 화면이 그려지는 기준은 `view`이고 이 값은 알림용이다. 성공하면 비운다. */
  error: ApiError | null
  /** 요청이 나가 있는 동안. 같은 버튼을 두 번 눌러도 command가 두 번 나가지 않게 한다. */
  busy: boolean
}

export interface FlowOptions {
  /** 진행 갱신 간격. web 구현값이다(§4) — web 리서치 문서는 2~3초를 권한다. */
  pollMs?: number
}

const INITIAL: FlowState = { caseId: null, view: null, uploads: [], error: null, busy: false }

/**
 * 반영 여부를 모르는 응답 — 응답 없음 · 500 · 게이트웨이 오류. 503은 「반영되지 않았다」가 계약이다(§3.4).
 * 이때는 POST를 다시 보내기 전에 GET /view로 확인한다.
 */
const unknownOutcome = (status: number) => status === 0 || (status >= 500 && status !== 503)

export function createCaseFlow(api: Api, { pollMs = 2000 }: FlowOptions = {}) {
  let state = INITIAL
  let active = false
  let commands = 0 // command를 보낸 횟수 — 읽기가 나간 뒤 command가 나갔는지 알아본다
  let timer: ReturnType<typeof setTimeout> | undefined
  const listeners = new Set<() => void>()

  const set = (patch: Partial<FlowState>) => {
    state = { ...state, ...patch }
    listeners.forEach((listener) => listener())
  }

  /**
   * 새 CaseView를 받는다. 늦게 도착한 옛 응답이 새 화면을 덮지 않게 `case_rev`가 줄면 버린다 —
   * 같은 값은 받는다(`case_rev`를 올리지 않는 변경이 있다, case-command §9).
   */
  function adopt(view: CaseView) {
    if (!state.view || view.case_rev >= state.view.case_rev) set({ view })
    schedule() // 옛 응답을 버려도 갱신은 이어가야 한다 — 안 그러면 폴링이 여기서 끊긴다.
  }

  /** `running_jobs`가 비어 있으면 멈춘다 — 그것이 「case가 더 기다리지 않는다」다(§5.4). */
  // ponytail: 고정 간격이다 — 오래 걸리는 분석에서 서버 부하가 보이면 간격을 점점 늘린다(backoff).
  function schedule() {
    clearTimeout(timer)
    timer = undefined
    if (active && state.caseId && state.view && state.view.running_jobs.length > 0) {
      timer = setTimeout(refresh, pollMs)
    }
  }

  async function refresh() {
    const caseId = state.caseId
    if (!caseId) return
    if (state.busy) return schedule() // command가 나가 있는 동안은 그 응답이 최신이다
    const sent = commands
    const res = await api.getView(caseId)
    // 그 사이 다른 case로 바뀌었거나 command가 나갔다 — 이 응답은 낡은 값일 수 있다.
    if (state.caseId !== caseId || sent !== commands) return schedule()
    if (res.ok) {
      set({ error: null })
      adopt(res.data)
      return
    }
    set({ error: res.error })
    if (res.status !== 404) schedule() // 일시 장애는 다음 주기에 다시 읽는다. case가 없으면(404) 멈춘다.
  }

  /** 새로고침 뒤 이어가기 — case id만 있으면 GET /view로 현재 화면을 읽는다. */
  async function resume(caseId: string) {
    set({ ...INITIAL, caseId, busy: true })
    const res = await api.getView(caseId)
    if (state.caseId !== caseId) return
    set({ busy: false })
    if (res.ok) adopt(res.data)
    else set({ error: res.error })
  }

  function patchUpload(index: number, status: UploadItem['status'], error: string | null = null) {
    set({ uploads: state.uploads.map((item, i) => (i === index ? { ...item, status, error } : item)) })
  }

  /** 파일 하나. 성공 · 실패를 `uploads`에 남기고 다음 파일로 계속한다(core-user-flow §23). */
  // ponytail: 실패한 파일을 다시 올리는 동작은 두지 않는다 — 사용자가 다시 고르면 같은 case에 이어 올린다(`addFiles`).
  async function upload(caseId: string, index: number, file: File) {
    const before = state.view?.manifest_summary.file_count ?? 0
    patchUpload(index, 'UPLOADING')
    const res = await api.uploadSource(caseId, file)
    if (state.caseId !== caseId) return
    if (res.ok) {
      adopt(res.data.case_view)
      return patchUpload(index, 'DONE')
    }
    // 반영 여부를 모르면 `file_count`로 확인한다. 이미 +1이면 등록된 것이라 다시 보내지 않는다(§5.2).
    if (unknownOutcome(res.status)) {
      const check = await api.getView(caseId)
      if (state.caseId !== caseId) return
      if (check.ok) {
        adopt(check.data)
        if (check.data.manifest_summary.file_count === before + 1) return patchUpload(index, 'DONE')
      }
    }
    patchUpload(index, 'FAILED', res.error.code)
  }

  /**
   * 영상을 하나씩 순서대로 올린다(§5.2). 첫 영상이면 case를 만들고, 이미 있으면 같은 case에 이어 올린다.
   * 분석은 시작하지 않는다 — `START_ANALYSIS`는 사용자가 누를 때 `send`로 보낸다(상황 설명이 그 payload다).
   */
  async function addFiles(files: File[]) {
    if (state.busy || files.length === 0) return
    const offset = state.uploads.length
    set({
      busy: true,
      error: null,
      uploads: [...state.uploads, ...files.map((file) => ({ name: file.name, status: 'WAITING' as const, error: null }))],
    })
    let caseId = state.caseId
    if (!caseId) {
      const created = await api.createCase()
      // 올린 파일이 없으니 「대기 중」으로 남기지 않는다 — 실패는 `error`가 알린다.
      if (!created.ok) return set({ busy: false, uploads: state.uploads.slice(0, offset), error: created.error })
      caseId = created.data.case_id
      set({ caseId, view: created.data.case_view })
    }
    for (let i = 0; i < files.length; i++) await upload(caseId, offset + i, files[i])
    if (state.caseId === caseId) set({ busy: false })
  }

  /** command 1건. `expected_case_rev`는 화면이 본 값이다 — 낡았으면 409와 현재 화면이 온다(§5.3). */
  async function send(command: Command) {
    const { caseId, view } = state
    if (!caseId || !view || state.busy) return
    commands++
    set({ busy: true, error: null })
    const res = await api.sendCommand(caseId, view.case_rev, command)
    if (state.caseId !== caseId) return
    if (res.ok) {
      adopt(res.data)
      return set({ busy: false })
    }
    if (res.caseView) adopt(res.caseView) // case가 실은 현재 화면 — 따로 다시 읽지 않는다(§3.2)
    set({ busy: false, error: res.error })
    // 반영 여부를 모르면 다시 보내지 않고 먼저 읽는다(§3.4).
    if (!res.caseView && unknownOutcome(res.status)) await refresh()
  }

  return {
    getState: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    /** 화면이 붙어 있는 동안만 진행을 갱신한다. 돌려준 함수로 끊는다. */
    connect() {
      active = true
      schedule()
      return () => {
        active = false
        clearTimeout(timer)
        timer = undefined
      }
    },
    addFiles,
    send,
    resume,
  }
}
