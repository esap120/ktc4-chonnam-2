import { useEffect, useState, type JSX } from 'react'
import type { CaseView } from '../contracts/caseView'
import { selectScreen } from '../state/selectScreen'
import { ProgressPanel } from '../components/ProgressPanel'

// Figma 02_Main_Flow · 02_Retry_Flow · 02_Fail_Flow. 세 프레임은 같은 틀이고
// 단계 상태(progress)와 알림(notices)만 다르다 — 둘 다 CaseView에서 온다.
// 진행 화면에는 버튼도 알림 문구도 없다. 실패는 그 단계를 빨갛게만 칠하고,
// 무슨 일이 있었는지는 결과 화면에서 알린다.
export function FlowScreen(props: {
  view: CaseView
  fileName: string
  situation: string
  startedAt: number
  title?: string
}): JSX.Element {
  const screen = selectScreen(props.view)
  // 장면 찾기가 끝나기 전에는 「찾는 중」, 끝나면 「준비 중」(core-user-flow §7·§19).
  const found = props.view.progress.some((p) => p.step === 'coarse_search' && p.state === 'DONE')
  // 경과 시간만 보여준다. 남은 시간·퍼센트는 내지 않는다(§7).
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const sec = Math.max(0, Math.floor((now - props.startedAt) / 1000))
  const elapsed = `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
  return (
    <div className="stack">
      <h1 className="page-title">{props.title ?? (found ? '신고자료를 준비하고 있어요' : '사건을 찾고 있어요')}</h1>
      <div className="panel panel-p tight run-summary">
        <b>{props.fileName}</b>
        {props.situation && <span className="kv-src">“{props.situation}”</span>}
      </div>
      <ProgressPanel view={props.view} jobs={screen.jobs} />
      <p className="kv-src">경과 시간 <span className="mono">{elapsed}</span></p>
    </div>
  )
}
