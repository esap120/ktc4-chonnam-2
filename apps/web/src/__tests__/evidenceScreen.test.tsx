// @vitest-environment jsdom
//
// 상황 응답 대기 중 부분 투영(case-view/v1.8, #239) — record_id=null이면 상황 종속 셋을
// 「알 수 없음」이 아니라 「응답 뒤에 정해져요」로 적는다.

import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { CaseView } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { EvidenceScreen } from '../screens/EvidenceScreen'

afterEach(cleanup)

const full = SNAPSHOTS.map((s) => s.view).find((v) => v.evidence?.record_id)!
const unknown = { code: null, label: null, needs_review: false, info_state: 'INFO_UNKNOWN' as const, source_label_key: null }
const partial: CaseView = {
  ...full,
  evidence: {
    ...full.evidence!,
    record_id: null,
    case_type_display: unknown,
    violation_display: unknown,
    report_type_display: unknown,
  },
  package: null,
}

it('부분 투영이면 상황 종속 셋만 「응답 뒤에 정해져요」로 적고 나머지 값은 그대로 보여 준다', () => {
  const { container } = render(<EvidenceScreen view={partial} hideOthers />)
  expect(container.textContent!.split('상황 응답 뒤에 정해져요').length - 1).toBe(3)
  expect(container.textContent).toContain(full.evidence!.plate_display.value ?? '알 수 없음')
})

it('EvidenceRecord가 있으면(record_id 있음) 그 문구를 쓰지 않는다', () => {
  const { container } = render(<EvidenceScreen view={full} hideOthers />)
  expect(container.textContent).not.toContain('상황 응답 뒤에 정해져요')
})
