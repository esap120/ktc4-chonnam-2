import { useState, type JSX } from 'react'
import { LOAD_ISSUES, SNAPSHOTS } from './contracts/fixtures'
import { CaseScreen } from './screens/CaseScreen'
import { DemoFlow } from './screens/DemoFlow'

// 기본은 시연 흐름(홈 → 진행 → 결과). `?dev`는 스냅샷을 하나씩 넘겨 보는 증빙 화면이다.
export function App(): JSX.Element {
  return new URLSearchParams(location.search).has('dev') ? <SnapshotViewer /> : <DemoFlow />
}

// 1차 범위에 라우터·서버·로컬 상태 머신이 없다. 화면 전환은 「어느 스냅샷을
// 보는가」뿐이다.
function SnapshotViewer(): JSX.Element {
  const [current, setCurrent] = useState(0)
  const view = SNAPSHOTS[current].view

  return (
    <div>
      <div className="snapshot-bar">
        {SNAPSHOTS.map((s, i) => (
          <button
            key={`${s.scenarioId}-${s.index}`}
            type="button"
            className={`btn${i === current ? ' on' : ''}`}
            onClick={() => setCurrent(i)}
          >
            {s.scenarioId.replace('scenario_', '').replace('_001', '')} #{s.index}
          </button>
        ))}
      </div>

      <main className="web-main">
        <div className="web-meta">
          <span className="kv-val mono">{view.case_id}</span>
          <span className="kv-src mono">rev {view.case_rev}</span>
          <span className={LOAD_ISSUES.length === 0 ? 'load-ok' : 'load-bad'}>
            스냅샷 {SNAPSHOTS.length}건 파싱 {LOAD_ISSUES.length === 0 ? 'OK' : `문제 ${LOAD_ISSUES.length}건`}
          </span>
        </div>

        <CaseScreen view={view} showReason />

        {LOAD_ISSUES.length > 0 && (
          <div className="panel panel-p tight">
            <div className="sec-label">계약과 어긋난 값</div>
            {LOAD_ISSUES.map((issue, i) => (
              <div className="kv-src mono" key={i}>
                {issue.where} — {issue.problem}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
