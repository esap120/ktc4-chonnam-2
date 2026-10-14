// @vitest-environment jsdom
//
// 시연 흐름: 파일 선택·버튼과 작업 상태 변화로만 화면이 넘어간다.

import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { CaseView } from '../contracts/caseView'
import { SNAPSHOTS } from '../contracts/fixtures'
import { DemoFlow } from '../screens/DemoFlow'
import { ResultScreen } from '../screens/ResultScreen'
import { StoppedScreen } from '../screens/StoppedScreen'

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function start(caseKey: string) {
  const r = render(<DemoFlow />)
  fireEvent.change(r.container.querySelector('select')!, { target: { value: caseKey } })
  fireEvent.change(r.container.querySelector('input[type=file]')!, {
    target: { files: [new File([''], 'a.mp4', { type: 'video/mp4' })] },
  })
  const text = () => r.container.querySelector('main')!.textContent!
  // 다음 타이머는 렌더 뒤 effect가 건다 — 한 번에 한 단계씩 흘린다.
  const wait = () => {
    for (let i = 0; i < 20; i++) act(() => vi.advanceTimersByTime(5_000))
  }
  // 결과 화면에서 신고 상황에 답하고 나머지 준비가 끝날 때까지 흘린다.
  const answer = (label = '맞아요') => {
    fireEvent.click(r.getByText(label))
    wait()
  }
  return { ...r, text, wait, answer }
}

it('정상: 업로드 완료 → 진행 → 신고 상황 응답 → 결과, 하위 화면은 「<」로 돌아온다', () => {
  const { text, wait, getByText, container } = start('main')
  expect(text()).toContain('올리는 중')
  wait()
  expect(text()).toContain('올리기 완료')
  fireEvent.click(getByText('영상에서 찾아보기'))
  expect(text()).toContain('경과 시간')
  wait()
  // 응답 전에는 신고자료 묶음이 없다 — 초안·제출 버튼 없이 상황 요약과 응답 버튼만
  expect(text()).toContain('신고 상황을 확인해 주세요')
  expect(text()).toContain('이 사건을 이렇게 정리했어요')
  expect(text()).not.toContain('안전신문고로 이동')
  // 응답에 따라 정해지는 값 셋은 응답 뒤로 미룬다
  expect(text()).toContain('상황 응답 뒤에 정해져요')
  fireEvent.click(getByText('맞아요'))
  expect(text()).toContain('신고자료를 준비하고 있어요')
  wait()
  expect(text()).toContain('신고자료가 준비됐어요')
  expect(text()).not.toContain('신고 상황을 확인해 주세요')
  // 최종 신고문(v1.7)은 case가 만든 제목·내용을 그대로 보여 준다
  expect(text()).toContain('진로변경 위반 차량 신고')
  expect(text()).toContain('백색 실선을 넘어 진로를 변경하는 것을 확인하여 신고합니다')
  // 시각은 보기 좋은 모양으로. 위치는 지도 없이 초안 행만 있다
  expect(text()).toContain('2026-08-24 18:05:12')
  expect(text()).not.toContain('T18:05')
  expect(text()).toContain('발생 장소')
  fireEvent.click(getByText('어떻게 정했는지 →'))
  expect(text()).toContain('어떻게 정했는지')
  fireEvent.click(container.querySelector('.back')!)
  expect(text()).toContain('신고자료가 준비됐어요')
})

it('번호판 판독 실패: 진행은 끝까지 흐르고 결과 화면에서 알리며 제출을 막는다', () => {
  const { wait, getByText, text } = start('plateFailed')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('신고자료를 완성하지 못했어요')
  expect(text()).toContain('번호판 판독에 실패했습니다')
  // package가 없으니 초안·제출 버튼은 없고, notice와 다시 시도만 있다
  expect(text()).not.toContain('안전신문고로 이동')
  // 번호판 다시 읽기 → 번호판부터 다시 진행해 정상 결과로 끝난다
  fireEvent.click(getByText('번호판 다시 읽기'))
  expect(text()).toContain('경과 시간')
  wait()
  expect(text()).toContain('신고자료가 준비됐어요')
})

it('위반 미관찰: 후보 확인에서 멈추고 번호판 판독은 시작하지 않는다', () => {
  const { wait, getByText, text, container } = start('notObserved')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  const seen = new Set<string>()
  for (let i = 0; i < 20; i++) {
    container.querySelectorAll('.tl-running .tl-label, .tl-done .tl-label').forEach((el) => seen.add(el.textContent!))
    act(() => vi.advanceTimersByTime(5_000))
  }
  expect(seen.has('후보 확인')).toBe(true)
  expect(seen.has('번호판 판독')).toBe(false)
  expect(text()).toContain('위반을 확인하지 못했어요')
})

it('결과 없음: 아래에서 다시 적고 다시 찾으면 새로 진행한다', () => {
  const { wait, getByText, text, container } = start('notFound')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('말씀하신 장면을 찾지 못했어요')
  const box = container.querySelector('textarea')!
  fireEvent.change(box, { target: { value: '' } })
  fireEvent.keyDown(box, { key: 'Tab' })
  expect(box.value).toContain('검은 승용차')
  fireEvent.click(getByText('다시 찾기'))
  expect(text()).toContain('경과 시간')
  wait()
  expect(text()).toContain('신고 상황을 확인해 주세요')
})

it('다른 후보: 기준 후보를 같이 놓되 버튼은 다른 후보에만 달고, 고르면 다시 준비한다', () => {
  const { wait, getByText, getAllByText, text, container, answer } = start('main')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  answer()
  fireEvent.click(getByText('다른 후보 영상 2 →'))
  expect(container.querySelectorAll('.cand')).toHaveLength(3)
  expect(text()).toContain('지금 신고자료 기준')
  expect(container.querySelector('.hint-recall')).not.toBeNull()
  expect(getAllByText('이 장면으로 다시 준비')).toHaveLength(2)
  // 2번 후보를 고르면 다시 준비한 뒤 2번이 기준 후보가 된다
  fireEvent.click(container.querySelector('.cand-col button')!)
  expect(text()).toContain('경과 시간')
  wait()
  // 새 후보에는 응답을 새로 받는다 — 이전 응답을 옮기지 않는다(§8-1)
  expect(text()).toContain('신고 상황을 확인해 주세요')
  answer()
  fireEvent.click(getByText('다른 후보 영상 2 →'))
  const cards = [...container.querySelectorAll('.cand')]
  expect(cards.map((c) => c.classList.contains('sel'))).toEqual([false, true, false])
})

it('업로드 실패: 다시 선택하면 다시 올린다', () => {
  const { wait, text } = start('uploadFail')
  wait()
  expect(text()).toContain('업로드 실패')
  expect(text()).toContain('다시 선택')
  expect(text()).toContain('파일을 올리지 못했어요')
})

it('설명이 비어 있으면 Tab이 예시를 채우고, 「새 신고」는 처음 화면으로 돌아간다', () => {
  const { container, getByText, text, wait, answer } = start('main')
  const box = container.querySelector('textarea')!
  fireEvent.keyDown(box, { key: 'Tab' })
  expect(box.value).toContain('흰색 SUV')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  answer()
  expect(text()).toContain('신고자료가 준비됐어요')
  fireEvent.click(getByText('새 신고'))
  expect(text()).toContain('블랙박스 영상을 올려주세요')
  expect(container.querySelector('textarea')!.value).toBe('')
})

it('번호판은 자세히 보기에서 읽은 값을 채운 채 고치고, 결과 화면에 「사용자 확인됨」으로 반영된다', () => {
  const { wait, getByText, text, container, answer } = start('main')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  answer()
  fireEvent.click(getByText('자세히 보기'))
  expect(text()).toContain('번호판을 읽은 장면')
  fireEvent.click(getByText('번호 수정'))
  const input = container.querySelector('.plate-input') as HTMLInputElement
  expect(input.value).toBe('12가3456')
  fireEvent.change(input, { target: { value: '12가3458' } })
  fireEvent.click(getByText('저장'))
  expect(text()).toContain('12가3458')
  fireEvent.click(container.querySelector('.back')!)
  expect(text()).toContain('12가3458')
  expect(text()).toContain('사용자 확인됨')
})

it('복사 버튼은 붙여넣을 칸에만 있다', () => {
  const { wait, getByText, container, answer } = start('main')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  answer()
  const rows = [...container.querySelectorAll('.kv-row.draft')]
  const withCopy = rows.filter((r) => r.textContent!.includes('복사')).map((r) => r.querySelector('.kv-k')!.textContent)
  // 제목·내용은 case가 만든 신고문(v1.7)이라 통째로 복사한다. 나머지는 붙여넣을 칸만이다
  expect(withCopy).toEqual(['제목', '내용', '차량 번호', '위반 내용'])
})

it('번호판 못 읽음: 경고만 달고 제출은 막지 않는다', () => {
  const { wait, getByText, text } = start('plateUnread')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('신고자료가 준비됐어요')
  expect(text()).toContain('번호판을 확정하지 못했습니다')
  expect((getByText('안전신문고로 이동') as HTMLButtonElement).disabled).toBe(false)
})

it('신고용 영상 미생성: 제출을 막고 「신고용 영상 만들기」로 만든다', () => {
  const { wait, getByText, text } = start('videoNotGenerated')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('신고자료를 완성하지 못했어요')
  expect(text()).toContain('신고용 영상이 아직 만들어지지 않았습니다')
  expect((getByText('안전신문고로 이동') as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(getByText('신고용 영상 만들기'))
  expect(text()).toContain('신고용 영상을 만들고 있어요')
  wait()
  expect(text()).toContain('신고자료가 준비됐어요')
})

it('장면 찾기 실패: 실패 화면에서 「다시 찾기」로 이어서 찾는다', () => {
  const { wait, getByText, text } = start('searchFailed')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('영상을 살펴보다가 문제가 생겼어요')
  fireEvent.click(getByText('다시 찾기'))
  expect(text()).toContain('장면을 다시 찾고 있어요')
  wait()
  expect(text()).toContain('신고 상황을 확인해 주세요')
})

it('분석 중단: 실패 화면이 아니라 중단 화면이고, 「다시 찾기」는 영상 전체를 새로 찾는다', () => {
  const { wait, getByText, text } = start('analysisStopped')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('분석을 중단했어요')
  expect(text()).not.toContain('문제가 생겼어요')
  fireEvent.click(getByText('다시 찾기'))
  expect(text()).toContain('장면을 다시 찾고 있어요')
  wait()
  expect(text()).toContain('신고 상황을 확인해 주세요')
})

it('분석 중단: 다시 찾을 근거가 없어 버튼이 없으면 처음부터 시작하라고 안내한다', () => {
  const searching = SNAPSHOTS.map((x) => x.view).find((v) => v.stage === 'SEARCHING')!
  const notice = { code: 'case.analysis_stopped', severity: 'INFO' as const, blocking: false, message_key: 'notice.analysis_stopped', actions: [] }
  const { container } = render(<StoppedScreen view={{ ...searching, notices: [notice] }} onAction={() => {}} />)
  expect(container.textContent).toContain('분석을 중단했어요')
  expect(container.textContent).toContain('새 신고')
  expect(container.querySelector('button')).toBeNull()
})

it('업로드 일부 실패: 건너뛴 파일을 알리고 나머지로 계속한다', () => {
  const { wait, getByText, text } = start('uploadPartial')
  wait()
  expect(text()).toContain('FILE_017.mp4')
  expect((getByText('영상에서 찾아보기') as HTMLButtonElement).disabled).toBe(false)
})

it('다른 후보를 고르면 「새 후보 기준으로」 다시 준비한다고 말한다', () => {
  const { wait, getByText, text, container, answer } = start('main')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  answer()
  fireEvent.click(getByText('다른 후보 영상 2 →'))
  fireEvent.click(container.querySelector('.cand-col button')!)
  expect(text()).toContain('새 후보 기준으로 신고자료를 다시 준비하고 있어요')
})

it('위반 미관찰: 다른 후보를 버튼 없이 바로 펼쳐 둔다', () => {
  const { wait, getByText, getAllByText, container } = start('notObserved')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(container.querySelectorAll('.cand')).toHaveLength(3)
  expect(getAllByText('이 장면으로 다시 준비')).toHaveLength(2)
})

it('신고 상황 「잘 모르겠어요」도 진행을 막지 않고, 다른 후보 입구는 응답 전에도 있다', () => {
  const { wait, answer, getByText, text } = start('main')
  wait()
  fireEvent.click(getByText('영상에서 찾아보기'))
  wait()
  expect(text()).toContain('다른 장면이었나요? 다른 후보 2 →')
  answer('잘 모르겠어요')
  expect(text()).toContain('신고자료가 준비됐어요')
})

it('응답 대기 중 evidence가 부분 투영돼도 신고용 영상 칸은 그리지 않고 확보한 번호판은 보여 준다 (v1.8)', () => {
  const full = SNAPSHOTS.map((x) => x.view).find((v) => v.evidence && v.package)!
  const view = {
    ...full,
    stage: 'EVIDENCE_REVIEW' as const,
    package: null,
    candidates: full.candidates.map((c) => (c.selected ? { ...c, situation_confirmation: 'NOT_ASKED' as const } : c)),
    notices: [
      { code: 'case.situation_response_pending', severity: 'INFO' as const, blocking: false, message_key: 'notice.situation_response_pending', actions: [] },
    ],
  }
  const noop = () => {}
  const { container } = render(
    <ResultScreen view={view} onCandidates={noop} onPlate={noop} onDetails={noop} onAction={noop} onRespond={noop} />,
  )
  expect(container.textContent).toContain('신고 상황을 확인해 주세요')
  expect(container.textContent).toContain(full.evidence!.plate_display.value!)
  expect(container.textContent).not.toContain('신고용 영상 · 원본에서')
})

it('package에 report가 없는 옛 판본이 와도 결과 화면이 깨지지 않는다', () => {
  const ready = SNAPSHOTS.map((x) => x.view).find((v) => v.stage === 'READY' && v.package)!
  const old = { ...ready, package: { ...ready.package!, report: undefined } } as unknown as CaseView
  const noop = () => {}
  const { container } = render(
    <ResultScreen view={old} onCandidates={noop} onPlate={noop} onDetails={noop} onAction={noop} />,
  )
  expect(container.textContent).toContain('안전신문고 신고서 초안')
  expect(container.textContent).not.toContain('제목')
})
