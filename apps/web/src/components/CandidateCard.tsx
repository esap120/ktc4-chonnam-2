import type { JSX } from 'react'
import type { Candidate } from '../contracts/caseView'
import { SITUATION_LABELS, atProvenanceLabel, formatValue, staleLabel } from '../contracts/labels'
import '../styles/candidates.css'

// 시각 출처는 `at_provenance_label_key`로만 고른다(case-view/v1.4 §7, PR #46
// Q-3). raw `at_provenance`는 authoritative지만 web이 해석하지 않으므로 화면에
// 내보내지 않는다. v5 fixture는 아직 키를 안 내려서 지금은 전부 fallback
// 문구가 뜬다 — 키가 들어오면 문구가 자동으로 바뀐다.
//
// 번호는 case가 준 `rank`다(#122). web이 순위를 계산하지 않는다. mock fixture처럼
// `rank`가 없으면 case가 준 배열 순서(`ordinal`, 1부터)를 그대로 쓴다.
//
// `selected`는 사용자가 고른 후보가 아니라 case가 자동 선택한 현재 초안의
// 기준 후보다(§8-1, #122). 태그 문구도 그 뜻으로 적는다.
export function CandidateCard(props: { candidate: Candidate; ordinal: number }): JSX.Element {
  const c = props.candidate
  const stale = staleLabel(c.stale_revision_label_key)
  return (
    <div className={`cand${c.selected ? ' sel' : ''}`}>
      <div className="cand-th">
        <span className="cand-th-note">미리보기 준비 중</span>
      </div>
      <div className="cand-b">
        <div className="cand-h">
          <span className="cnum">{c.rank ?? props.ordinal}</span>
          <span className="cand-tc">{c.at === null ? '시각 미확정' : formatValue(c.at)}</span>
          {c.selected && <span className="cand-tag">지금 신고자료 기준</span>}
        </div>
        {c.stale_revision && stale && <span className="badge badge-unknown sm">{stale}</span>}
        <p className="cand-obs">{c.observed}</p>
        <dl className="cand-meta">
          <div>
            <dt>상황 확인</dt>
            <dd>{SITUATION_LABELS[c.situation_confirmation]}</dd>
          </div>
          <div>
            <dt>시각 출처</dt>
            <dd>{atProvenanceLabel(c.at_provenance_label_key)}</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}
