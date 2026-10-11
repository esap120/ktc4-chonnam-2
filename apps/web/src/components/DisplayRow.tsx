import type { JSX, ReactNode } from 'react'
import type { InfoState } from '../contracts/caseView'
import { formatValue, sourceLabel } from '../contracts/labels'
import { StatusBadge } from './StatusBadge'

// 값 상태 표시 규칙(docs/modules/web/ux/value-state-display.md)의 구현 지점.
//
// §2  분기는 info_state로만 한다. needs_review를 직접 해석하지 않는다.
// §3-1 AI 추정·확인 필요는 확정값과 시각적으로 구분한다(배지 + 행 배경).
// §3-2 출처를 값과 같은 화면에 둔다. source_label_key로 문구를 고른다.
// §3-3 UNKNOWN은 빈 칸이 아니다 — 「알 수 없음」과 단서를 보여준다.
// §3-4 값을 합치거나 새로 만들지 않는다.

const TINT: Partial<Record<InfoState, string>> = {
  INFO_NEEDS_REVIEW: 'act',
  INFO_AI_ESTIMATED: 'est',
}

export function DisplayRow(props: {
  label: string
  value: string | null
  infoState: InfoState
  sourceLabelKey: string | null
  /** UNKNOWN일 때 함께 보여줄 단서(§3-3) */
  clue?: ReactNode
}): JSX.Element {
  const unknown = props.infoState === 'INFO_UNKNOWN'
  const source = sourceLabel(props.sourceLabelKey)
  const rowClass = ['kv-row', TINT[props.infoState]].filter(Boolean).join(' ')
  const valueClass = ['kv-val', unknown ? 'unk' : undefined].filter(Boolean).join(' ')

  return (
    <div className={rowClass}>
      <span className="kv-k">{props.label}</span>
      <span className="kv-v">
        <span className={valueClass}>{props.value === null ? '알 수 없음' : formatValue(props.value)}</span>
        {source && <span className="kv-src">{source}</span>}
        {unknown && props.clue && <span className="kv-src">{props.clue}</span>}
      </span>
      <StatusBadge state={props.infoState} />
    </div>
  )
}
