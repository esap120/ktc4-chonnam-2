import type { JSX } from 'react'
import type { CaseView } from '../contracts/caseView'
import { HINT_LABELS, HINT_NONE, HINT_ORDER } from '../contracts/labels.candidate'
import '../styles/candidates.css'

// 사용자가 말한 기억 단서를 후보 목록 위에 한 번 띄운다
// (`core-user-flow.md` §8-2 「사용자가 입력한 기억 단서」). 후보 목록은 결과
// 화면의 「다른 후보 보기」에서 열리므로(§8-1) 단서도 그 안에서만 보인다.
//
// **대조하지 않는다.** 단서가 후보와 맞는지 화면이 정하면 판정 재계산이다 —
// `hints`는 문자열 4개고 `candidates[].observed`는 문장 하나인데, 둘이 같은
// 것을 가리키는지 판단하는 값이 `CaseView`에 없다. §8-2도 「시간·차량·상황이
// 어긋나는지는 화면이 추론하지 않는다」고 적는다. `✓`·`✗` 대조는 어느 모듈도
// 만들지 않기로 하고 MVP 밖으로 뺐다(#122, 9/27).
//
// 그래서 지금은 나란히 놓기만 한다. 단서는 여기, AI가 본 것은 각 카드의
// `observed`에 있고, 짝은 위치로만 만든다. 판단은 사람이 한다.
//
// 카드마다 반복하지 않는 이유도 같다. `hints`는 사건 단위 값이라 카드 3장에
// 같은 「흰색 SUV」를 세 번 적으면 후보별 정보처럼 보인다 — 대조를 안 한다면서
// 대조한 것처럼 읽힌다.
export function HintRecall(props: { hints: CaseView['hints']; description?: CaseView['description'] }): JSX.Element {
  // 계약상 네 키는 항상 있지만 실제 산출물이 `{}`로 오는 사례가 있었다(이슈
  // #103). 키가 없는 것과 값이 null인 것을 같게 다룬다.
  const given = HINT_ORDER.filter((key) => props.hints?.[key])
  // 단서 구조화가 안 됐어도(진행 중·실패) 사용자가 적은 원문은 그대로 보여 준다(v1.7, #259).
  // 원문을 web이 해석하거나 나누지 않는다.
  const original = props.description?.trim() ? props.description : null

  return (
    <div className="hint-recall">
      <div className="sec-label">기억하신 것</div>
      {given.length === 0 && original ? (
        <span className="hint-original" style={{ whiteSpace: 'pre-wrap' }}>
          {original}
        </span>
      ) : given.length === 0 ? (
        <span className="hint-none">{HINT_NONE}</span>
      ) : (
        <ul className="hint-chips">
          {given.map((key) => (
            <li key={key} className="hint-chip">
              <span className="hint-chip-k">{HINT_LABELS[key]}</span>
              <span className="hint-chip-v">{props.hints[key]}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
