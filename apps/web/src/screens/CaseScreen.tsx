import { useEffect, useState, type JSX } from 'react'
import type { Action, CaseView } from '../contracts/caseView'
import { describeIntent } from '../contracts/actionIntent'
import { selectScreen } from '../state/selectScreen'
import { DevExtra } from '../components/DevExtra'
import { NoticeList } from '../components/NoticeList'
import { ProgressPanel } from '../components/ProgressPanel'
import { CandidatesScreen } from './CandidatesScreen'
import { EvidenceScreen } from './EvidenceScreen'
import { HandoffScreen } from './HandoffScreen'
import { NoResultScreen } from './NoResultScreen'
import { NotObservedScreen } from './NotObservedScreen'
import { OtherCandidates } from '../components/OtherCandidates'

// CaseView 1건 → 화면. 화면 내용은 전부 그 CaseView에서 파생된다.
export function CaseScreen(props: { view: CaseView; showReason?: boolean }): JSX.Element {
  const { view } = props
  // 발주 경로(case worker)가 아직 없다. 버튼이 아무 일도 안 하는 것처럼 보이지
  // 않게, 계약이 정한 「이 버튼이 무엇을 발주하는가」를 그대로 보여준다.
  // 실제 전송이 붙는 자리는 이 setState 하나다.
  const [lastAction, setLastAction] = useState<Action | null>(null)
  useEffect(() => setLastAction(null), [view])
  const screen = selectScreen(view)

  return (
    <>
      {props.showReason && <span className="kv-src">{screen.reason}</span>}

      <NoticeList blocking={screen.blocking} info={screen.info} onAction={setLastAction} />

      {lastAction && (
        <div className="panel panel-p tight action-intent">
          <div className="sec-label">눌린 액션 — 발주 경로 미연결</div>
          <div className="kv-val mono">{lastAction}</div>
          <div className="kv-src">{describeIntent(lastAction)}</div>
        </div>
      )}

      {screen.kind === 'PROGRESS' && <ProgressPanel view={view} jobs={screen.jobs} />}
      {screen.kind === 'NO_RESULT' && <NoResultScreen view={view} />}
      {screen.kind === 'NOT_OBSERVED' && (
        <>
          <NotObservedScreen view={view} />
          <OtherCandidates view={view} />
        </>
      )}
      {screen.kind === 'CANDIDATES' && <CandidatesScreen view={view} />}
      {screen.kind === 'EVIDENCE' && (
        <>
          <EvidenceScreen view={view} />
          <DevExtra label="증빙용 — 진행 상태(제품 화면에서는 별도 표시)">
            <ProgressPanel view={view} jobs={screen.jobs} />
          </DevExtra>
        </>
      )}
      {screen.kind === 'HANDOFF' && (
        <>
          <HandoffScreen view={view} />
          <DevExtra label="증빙용 — 확인한 내용(제품 화면에서는 이전 단계)">
            <EvidenceScreen view={view} />
          </DevExtra>
        </>
      )}
    </>
  )
}
