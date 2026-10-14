import type { JSX } from 'react'
import { isAction, type Action, type CaseView } from '../contracts/caseView'
import { ACTION_LABELS, noticeMessage } from '../contracts/labels'

// 사용자가 분석을 중단한 상태(case.analysis_stopped, #342). 실패가 아니라 사용자 행동의 결과다.
// 부분 후보는 남기지 않는다 — 다시 찾으면 영상 전체를 새로 본다(core-user-flow §7 현재 범위).
// 다시 찾을 근거가 없으면 case가 버튼을 싣지 않는다(단서 정리 중 중단) — 그때는 처음부터 시작한다.
export function StoppedScreen(props: { view: CaseView; onAction: (noticeCode: string, action: Action) => void }): JSX.Element {
  // 이 화면은 notice가 있을 때만 그린다(selectScreen `STOPPED`).
  const stopped = props.view.notices.find((n) => n.code === 'case.analysis_stopped')!
  const actions = stopped.actions.filter(isAction)
  return (
    <div className="stack">
      <h1 className="page-title">신고자료</h1>
      <section className="panel panel-p stack">
        <h2 className="panel-t">{noticeMessage(stopped.message_key)}</h2>
        <p className="kv-src">
          {actions.length > 0
            ? '올린 영상은 그대로예요. 다시 찾으면 영상 전체를 처음부터 살펴볼게요.'
            : '「새 신고」로 처음부터 다시 시작할 수 있어요.'}
        </p>
        {actions.length > 0 && (
          <div className="btnrow">
            {actions.map((a) => (
              <button key={a} type="button" className="btn pri" onClick={() => props.onAction(stopped.code, a)}>
                {ACTION_LABELS[a]}
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
