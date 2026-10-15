import { useEffect, useState, type JSX } from 'react'
import { createApi, type Api, type Command } from '../api/client'
import { AppHeader } from '../components/AppHeader'
import type { Action, CaseView } from '../contracts/caseView'
import { errorMessage } from '../contracts/labels'
import { selectScreen } from '../state/selectScreen'
import { useCaseFlow } from '../state/useCaseFlow'
import { FailedScreen } from './FailedScreen'
import { FlowScreen } from './FlowScreen'
import { NoResultScreen } from './NoResultScreen'
import { NotObservedScreen } from './NotObservedScreen'
import { ResultScreen } from './ResultScreen'
import { StoppedScreen } from './StoppedScreen'
import { CandidateCompare, DetailsCheck, PlateCheck } from './SubScreens'
import { UploadScreen, type UploadState } from './UploadScreen'

// 실제 HTTP API(`?api`)로 도는 흐름 — 시연(DemoFlow)과 같은 화면을 쓰고, 어느 화면인가는 CaseView가 정한다.
// 로컬에 둔 것은 사용자가 고른 파일 · 입력한 설명 · 열어 둔 하위 화면뿐이다(web-stack.md 확정 4).
// 화면 → command 연결은 `contract-case-command.md`를, 요청 · 재시도 규칙은 `contract-http-api.md` §6을 따른다.

type Sub = 'candidates' | 'plate' | 'details'
type NoticeAction = Extract<Command, { kind: 'RUN_NOTICE_ACTION' }>['payload']['action']

// notice 버튼 중 command가 있는 것만 보낸다. 나머지(직접 입력류)는 입력형 command가 아직 없다(#212 · #217).
const SENDABLE: ReadonlySet<string> = new Set<NoticeAction>([
  'GENERATE_REPORT_VIDEO',
  'RETRY_PLATE_READ',
  'RETRY_SEARCH',
  'GENERATE_PLATE_IMAGE',
])

export function ApiFlow(props: { api?: Api; caseId?: string | null }): JSX.Element {
  const [api] = useState(() => props.api ?? createApi())
  const { state, addFiles, send, resume } = useCaseFlow(api)
  const { view } = state
  const [situation, setSituation] = useState('')
  const [subs, setSubs] = useState<Sub[]>([])
  const [startedAt, setStartedAt] = useState(() => Date.now())
  const [unsupported, setUnsupported] = useState(false)

  // 주소의 case id로 이어간다. 새로 만든 case는 주소에 남겨 새로고침해도 이어진다.
  // ponytail: 경과 시간은 이어받은 시점부터 다시 센다 — CaseView에 시작 시각이 없다.
  const { caseId } = props
  useEffect(() => {
    if (caseId) void resume(caseId)
  }, [caseId, resume])
  useEffect(() => {
    if (!state.caseId) return
    const url = new URL(location.href)
    url.searchParams.set('case', state.caseId)
    history.replaceState(null, '', url)
  }, [state.caseId])

  const run = (command: Command) => {
    setUnsupported(false)
    void send(command)
  }
  const onAction = (noticeCode: string, action: Action) => {
    if (!SENDABLE.has(action)) return setUnsupported(true)
    run({ kind: 'RUN_NOTICE_ACTION', payload: { notice_code: noticeCode, action: action as NoticeAction } })
  }
  const reselect = (candidateId: string) => {
    setSubs([])
    run({ kind: 'SELECT_OTHER_CANDIDATE', payload: { candidate_id: candidateId } })
  }
  const respond = (value: 'CONFIRMED' | 'USER_UNSURE') => run({ kind: 'RECORD_SITUATION_RESPONSE', payload: { value } })
  const open = (sub: Sub) => setSubs((s) => [...s, sub])
  const back = () => setSubs((s) => s.slice(0, -1))
  const sub = subs[subs.length - 1]

  const banner = state.error ? errorMessage(state.error.code) : unsupported ? '이 동작은 아직 연결되지 않았어요.' : null

  return (
    <>
      <AppHeader onNewReport={() => location.assign(`${location.pathname}?api`)} />
      <main className="web-main">
        {banner && (
          <div className="flow-notice blocking" role="alert">
            {banner}
          </div>
        )}
        {!view || view.stage === 'INTAKE' ? upload() : analysis(view)}
      </main>
    </>
  )

  // 아래 둘은 컴포넌트가 아니라 함수로 부른다 — 컴포넌트로 두면 렌더마다 새로 만들어져 입력칸 · 타이머가 초기화된다.
  // 올리기 — 영상은 고르는 순간 올라가고(case는 첫 영상에서 만든다), 분석은 [영상에서 찾아보기]에서 시작한다.
  function upload(): JSX.Element {
    const uploads = state.uploads
    // 이어받은 case에는 이번 화면에서 올린 기록이 없다 — 서버에 이미 있는 영상은 개수로 보인다(이름은 오지 않는다).
    // `ok_file_count`만 본다. `failed_file_count`는 화면 판단에 쓰지 않는다(http-api §5.2).
    const already = uploads.length === 0 ? (view?.manifest_summary.ok_file_count ?? 0) : 0
    const uploading = uploads.some((u) => u.status === 'WAITING' || u.status === 'UPLOADING')
    const anyDone = already > 0 || uploads.some((u) => u.status === 'DONE')
    const uploadState: UploadState = uploading ? 'uploading' : anyDone ? 'done' : uploads.length > 0 ? 'fail' : 'idle'
    return (
      <UploadScreen
        state={uploadState}
        files={already > 0 ? [{ name: `이미 올린 영상 ${already}개` }] : uploads}
        skipped={uploads.filter((u) => u.status === 'FAILED').map((u) => u.name)}
        situation={situation}
        onFiles={(picked) => void addFiles(picked)} // 올리는 중에 고른 파일은 store가 받지 않는다
        onSituation={setSituation}
        onSearch={() => {
          setStartedAt(Date.now())
          run({ kind: 'START_ANALYSIS', payload: { description: situation } })
        }}
      />
    )
  }

  function analysis(view: CaseView): JSX.Element {
    const screen = selectScreen(view)
    switch (screen.kind) {
      case 'PROGRESS':
        return (
          <FlowScreen
            view={view}
            fileName={
              state.uploads.length
                ? state.uploads.filter((u) => u.status === 'DONE').map((u) => u.name).join(', ')
                : `영상 ${view.manifest_summary.ok_file_count}개`
            }
            situation={situation || view.description || ''}
            startedAt={startedAt}
            onStop={view.stage === 'SEARCHING' ? () => run({ kind: 'STOP_ANALYSIS', payload: {} }) : undefined}
          />
        )
      case 'STOPPED':
        return <StoppedScreen view={view} onAction={onAction} />
      case 'SEARCH_FAILED':
        return <FailedScreen view={view} onAction={onAction} />
      // ponytail: 다시 찾기 입력은 두지 않는다 — 설명을 고쳐 다시 찾는 command(EDIT_HINT)가 아직 없다. 「새 신고」로 다시 시작한다.
      case 'NO_RESULT':
        return <NoResultScreen view={view} />
      case 'NOT_OBSERVED':
        return <NotObservedScreen view={view} onSelect={reselect} />
      default:
        if (sub === 'candidates') return <CandidateCompare view={view} onBack={back} onSelect={reselect} />
        if (sub === 'plate') return <PlateCheck view={view} onBack={back} />
        if (sub === 'details') return <DetailsCheck view={view} onBack={back} />
        return (
          <ResultScreen
            view={view}
            onCandidates={() => open('candidates')}
            onPlate={() => open('plate')}
            onDetails={() => open('details')}
            onRespond={respond}
            onAction={onAction}
          />
        )
    }
  }
}
