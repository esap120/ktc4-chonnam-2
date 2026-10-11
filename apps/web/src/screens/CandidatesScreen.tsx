import type { JSX } from 'react'
import type { CaseView } from '../contracts/caseView'
import { CandidateCard } from '../components/CandidateCard'
import { HintRecall } from '../components/HintRecall'
import { Panel } from '../components/Panel'

// 후보를 세로로 쌓지 않고 나란히 놓는다(core-user-flow.md §8-2). 배열 순서를
// 그대로 그린다 — 정렬·순위 재계산은 case가 소유한 판정이다.
//
// 기억 단서는 후보 위에 한 번 놓는다. 대조는 하지 않는다(HintRecall 주석).
//
// onSelect가 있으면 기준 후보가 아닌 카드 아래에 「이 장면으로 다시 준비」를 단다
// (§8-1, SELECT_OTHER_CANDIDATE #216). 기준 후보는 버튼 없이 같이 놓아 비교 기준이 된다.
export function CandidatesScreen(props: { view: CaseView; onSelect?: (candidateId: string) => void }): JSX.Element {
  const { onSelect } = props
  return (
    <Panel title="찾은 장면">
      <HintRecall hints={props.view.hints} description={props.view.description} />
      <div className="cands">
        {props.view.candidates.map((c, i) => {
          const card = <CandidateCard key={c.candidate_id} candidate={c} ordinal={i + 1} />
          if (!onSelect) return card
          return (
            <div key={c.candidate_id} className="cand-col">
              {card}
              {!c.selected && (
                <button type="button" className="btn sm pri" onClick={() => onSelect(c.candidate_id)}>
                  이 장면으로 다시 준비
                </button>
              )}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
