import type { JSX } from 'react'
import type { CaseView, EvidenceView } from '../contracts/caseView'
import { DisplayRow } from '../components/DisplayRow'
import { OtherCandidates } from '../components/OtherCandidates'
import { Panel } from '../components/Panel'
import { reviewReason } from '../contracts/labels'

function locationClue(view: CaseView, evidence: EvidenceView): string | null {
  // §3-3 UNKNOWN은 빈 칸이 아니다 — hints.location · coord · search_keyword를
  // 단서로 함께 보여준다. 값을 이어 붙여 새 위치 문자열을 만들지는 않는다(§3-4).
  const parts: string[] = []
  if (view.hints.location) parts.push(`말한 위치: ${view.hints.location}`)
  const coord = evidence.location_display.coord
  if (coord) parts.push(`좌표: ${coord.lat}, ${coord.lon}`)
  if (evidence.location_display.search_keyword) {
    parts.push(`검색어: ${evidence.location_display.search_keyword}`)
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

export function EvidenceScreen(props: { view: CaseView; hideOthers?: boolean }): JSX.Element {
  const evidence = props.view.evidence
  if (!evidence) return <Panel title="증거 정리 전">아직 표시할 값이 없습니다.</Panel>

  // 결과 화면이므로 「다른 후보 보기」 출구를 함께 둔다(core-user-flow.md §8-1).
  return (
    <div className="stack">
      <Panel title="확인한 내용">
        <div className="kv kv-rows">
          <DisplayRow
            label="차량 번호"
            value={evidence.plate_display.value}
            infoState={evidence.plate_display.info_state}
            sourceLabelKey={evidence.plate_display.source_label_key}
          />
          <DisplayRow
            label="발생 시각"
            value={evidence.event_time_display.value}
            infoState={evidence.event_time_display.info_state}
            sourceLabelKey={evidence.event_time_display.source_label_key}
            clue={props.view.hints.time ? `말한 시각: ${props.view.hints.time}` : null}
          />
          <DisplayRow
            label="발생 장소"
            value={evidence.location_display.value}
            infoState={evidence.location_display.info_state}
            sourceLabelKey={evidence.location_display.source_label_key}
            clue={locationClue(props.view, evidence)}
          />
          <DisplayRow
            label="사건 분류"
            value={evidence.case_type_display.label}
            infoState={evidence.case_type_display.info_state}
            sourceLabelKey={evidence.case_type_display.source_label_key}
          />
          <DisplayRow
            label="위반 내용"
            value={evidence.violation_display.label}
            infoState={evidence.violation_display.info_state}
            sourceLabelKey={evidence.violation_display.source_label_key}
          />
          <DisplayRow
            label="신고 유형"
            value={evidence.report_type_display.label}
            infoState={evidence.report_type_display.info_state}
            sourceLabelKey={evidence.report_type_display.source_label_key}
          />
        </div>
        {evidence.review_needed && (
          // §3-6 요약 배지로만 쓴다 — 제출 게이트로 쓰지 않는다.
          // 원인은 reason_code로 고르되 raw 코드를 화면에 내보내지 않는다.
          <div className="kv-src" style={{ marginTop: 10 }}>
            {reviewReason(evidence.reason_code)}
          </div>
        )}
      </Panel>
      {!props.hideOthers && <OtherCandidates view={props.view} />}
    </div>
  )
}
