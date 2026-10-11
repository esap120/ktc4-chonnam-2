import type { JSX } from 'react'

export function AppHeader(props: { onNewReport: () => void }): JSX.Element {
  return (
    <header className="app-header">
      <span className="brand">
        <span className="brand-name">대신고</span>
        <span className="brand-sub">신고할 순간을 대신 찾아드립니다</span>
      </span>
      <nav>
        <button type="button" className="nav-link" onClick={props.onNewReport}>
          새 신고
        </button>
      </nav>
    </header>
  )
}
