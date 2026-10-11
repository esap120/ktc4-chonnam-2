import type { JSX } from 'react'
import { isAction, type Action, type CaseView } from '../contracts/caseView'
import { ACTION_LABELS, noticeMessage } from '../contracts/labels'

// 시스템 실패(core-user-flow §23). AI의 낮은 확신과 다르다 — 「후보 없음」으로 보여 주지
// 않는다(#197). 다시 시도는 처음부터가 아니라 실패한 단계부터 이어서 한다.
export function FailedScreen(props: { view: CaseView; onAction: (noticeCode: string, action: Action) => void }): JSX.Element {
  const blocking = props.view.notices.filter((n) => n.blocking)
  return (
    <div className="stack">
      <h1 className="page-title">신고자료</h1>
      <section className="panel panel-p stack">
        <h2 className="panel-t">영상을 살펴보다가 문제가 생겼어요.</h2>
        <p className="kv-src">지금까지 끝난 작업은 저장돼 있어요. 다시 시도하면 멈춘 곳부터 이어서 할게요.</p>
        {blocking.map((n) => (
          <div key={n.code} className="flow-notice blocking">
            {noticeMessage(n.message_key)}
            {n.actions.filter(isAction).map((a) => (
              <button key={a} type="button" className="btn sm notice-action" onClick={() => props.onAction(n.code, a)}>
                {ACTION_LABELS[a]}
              </button>
            ))}
          </div>
        ))}
      </section>
    </div>
  )
}
