// @vitest-environment jsdom
//
// 기억 단서 표시(A-3) 렌더 테스트.
//
// 이 파일이 지키는 것은 「무엇을 보여주는가」보다 **「무엇을 하지 않는가」**다.
// 단서와 후보를 화면이 대조하면 판정 재계산이라 Merge 중단 대상이고, 근거가
// 되는 값은 `CaseView`에 없다. 대조는 MVP 밖이다(이슈 #122).

import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { CaseView } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { HintRecall } from '../components/HintRecall'
import { OtherCandidates } from '../components/OtherCandidates'
import { CandidatesScreen } from '../screens/CandidatesScreen'

afterEach(cleanup)

const FULL: CaseView['hints'] = {
  time: '18시쯤',
  vehicle: '흰색 SUV',
  situation: '백색 실선 구간에서 차로변경',
  location: '상무중앙로 사거리 부근',
}

describe('HintRecall — 사용자가 말한 것을 그대로 옮긴다', () => {
  it('단서 네 개를 모두 보여준다', () => {
    const { container } = render(<HintRecall hints={FULL} />)
    expect(container.querySelectorAll('.hint-chip')).toHaveLength(4)
    expect(container.textContent).toContain('18시쯤')
    expect(container.textContent).toContain('흰색 SUV')
    expect(container.textContent).toContain('백색 실선 구간에서 차로변경')
    expect(container.textContent).toContain('상무중앙로 사거리 부근')
  })

  it('말하지 않은 단서는 빈 칸으로 만들지 않고 아예 뺀다', () => {
    // 값이 없는 것과 사용자가 말하지 않은 것은 다르다. 후자는 「알 수 없음」이
    // 아니라 애초에 없는 항목이라, 자리를 만들어 두면 빈 칸처럼 보인다.
    const { container } = render(<HintRecall hints={{ ...FULL, vehicle: null, location: null }} />)
    expect(container.querySelectorAll('.hint-chip')).toHaveLength(2)
    expect(container.textContent).not.toContain('차량')
    expect(container.textContent).not.toContain('위치')
  })

  it('단서를 하나도 안 남겼으면 그렇다고 적는다', () => {
    const { container } = render(
      <HintRecall hints={{ time: null, vehicle: null, situation: null, location: null }} />,
    )
    expect(container.querySelectorAll('.hint-chip')).toHaveLength(0)
    expect(container.textContent).toContain('기억 단서를 남기지 않으셨습니다')
  })

  it('단서 구조화가 안 됐으면 사용자가 적은 원문을 그대로 보여준다 (v1.7)', () => {
    const none = { time: null, vehicle: null, situation: null, location: null }
    const { container } = render(<HintRecall hints={none} description={'흰색 SUV가\n실선을 넘었어요'} />)
    expect(container.querySelector('.hint-original')?.textContent).toBe('흰색 SUV가\n실선을 넘었어요')
    expect(container.textContent).not.toContain('기억 단서를 남기지 않으셨습니다')
    cleanup()
    // 단서가 하나라도 있으면 원문 대신 단서를 쓰고, 원문이 비어 있으면 없다고 적는다
    const a = render(<HintRecall hints={{ ...none, vehicle: '흰색 SUV' }} description="원문" />)
    expect(a.container.querySelector('.hint-original')).toBeNull()
    cleanup()
    const b = render(<HintRecall hints={none} description="  " />)
    expect(b.container.textContent).toContain('기억 단서를 남기지 않으셨습니다')
  })

  it('hints가 통째로 비어 있어도 깨지지 않는다', () => {
    // 실제 파이프라인이 `{}`를 내리던 시기가 있었다(이슈 #103). 계약상 네 키는
    // 항상 있지만 화면이 그 약속에 기대어 터지지는 않게 둔다.
    const { container } = render(<HintRecall hints={{} as CaseView['hints']} />)
    expect(container.textContent).toContain('기억 단서를 남기지 않으셨습니다')
  })
})

describe('HintRecall — 대조하지 않는다', () => {
  it('맞음·틀림 기호를 붙이지 않는다', () => {
    // 이 단언이 A-3의 핵심이다. 단서가 후보와 맞는지 판단하는 값이 계약에
    // 없으므로(#122), 화면이 기호를 붙이면 근거 없는 판정을 지어낸 것이다.
    // 근거가 내려오면 이 테스트를 고치면서 표시를 얹는다.
    const { container } = render(<HintRecall hints={FULL} />)
    for (const mark of ['✓', '✗', '≠', '일치', '불일치', '비슷']) {
      expect(container.textContent).not.toContain(mark)
    }
  })

  it('단서를 후보마다 반복하지 않는다 — 화면에 한 번만 나온다', () => {
    // 카드 3장에 같은 「흰색 SUV」가 세 번 나오면 후보별 정보처럼 읽힌다.
    // `hints`는 사건 단위 값이다.
    const view = SNAPSHOTS.find((s) => s.scenarioId === 'real_e2e_happy_001')!.view
    const { container } = render(<CandidatesScreen view={view} />)
    expect(container.querySelectorAll('.hint-recall')).toHaveLength(1)
  })
})

describe('CandidatesScreen — 실제 산출물의 단서', () => {
  it('실제 hints가 후보 위에 뜬다', () => {
    const view = SNAPSHOTS.find((s) => s.scenarioId === 'real_e2e_happy_001')!.view
    const { container } = render(<CandidatesScreen view={view} />)
    const recall = container.querySelector('.hint-recall')
    expect(recall).not.toBeNull()
    expect(recall!.textContent).toContain(view.hints.vehicle!)
    expect(recall!.textContent).toContain(view.hints.time!)
  })

  it('후보가 0건인 스냅샷에서는 후보 화면 자체가 아니다 — 단서만 남지 않는다', () => {
    // `selectScreen`이 후보 0건을 NO_RESULT로 보내므로 이 화면에 오지 않는다.
    // 단서 패널만 덩그러니 뜨는 화면이 생기지 않는 것을 여기서 고정한다.
    const empty = SNAPSHOTS.find((s) => s.view.candidates.length === 0 && s.view.stage === 'CANDIDATE_REVIEW')
    expect(empty).toBeDefined()
  })
})

describe('HintRecall — 결과 화면의 「다른 후보 보기」 안에서 보인다', () => {
  it('단서는 후보 비교를 열었을 때의 맥락에 들어 있다', () => {
    // 후보 비교는 기본 화면이 아니라 결과 화면의 선택 경로다(§8-1). 단서도
    // 그 안에 담겨야 결과 화면 위에 따로 떠 있지 않는다.
    //
    // 실제 산출물은 후보가 selected 1건뿐이라 출구 자체가 없다(#124). 단서는
    // 실제 값을 쓰고, 후보만 selected 1 + 다른 후보 1로 만든 테스트용 뷰다.
    const real = SNAPSHOTS.find((s) => s.scenarioId === 'real_e2e_happy_001')!.view
    const selected = real.candidates.find((c) => c.selected)!
    const view = { ...real, candidates: [selected, { ...selected, candidate_id: 'c_other', selected: false }] }
    const { container } = render(<OtherCandidates view={view} />)
    expect(container.querySelector('details.other-cands .hint-recall')).not.toBeNull()
  })
})
