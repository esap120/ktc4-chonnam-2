// 화면 선택 — `stage × progress × running_jobs × notices`의 파생 함수.
//
// 로컬 step 상태를 두지 않는다(web-stack.md 확정 4). 진행 게이트를 화면이
// 계산하지 않는다 — stage·user_reviewed·readiness는 전부 case가 소유한다.
// 이 함수는 이미 내려온 값을 읽어 「어느 화면인가」만 고른다.

import type { CaseView, Notice, RunningJob } from '../contracts/caseView'

export type ScreenKind =
  | 'PROGRESS'
  | 'NO_RESULT'
  | 'NOT_OBSERVED'
  | 'AWAIT_RESPONSE'
  | 'CANDIDATES'
  | 'EVIDENCE'
  | 'HANDOFF'

export interface Screen {
  kind: ScreenKind
  /** 왜 이 화면인가 — 증빙 화면에 그대로 띄운다 */
  reason: string
  blocking: Notice[]
  info: Notice[]
  jobs: RunningJob[]
}

/**
 * 같은 job_id가 여러 번 오면 대표 하나만 남긴다(계약 A절 §10-6).
 * CaseView.running_jobs에는 attempt 필드가 없으므로, attempt가 실려 오면 가장
 * 큰 것을, 없으면 나중에 온 것을 대표로 본다. 어느 쪽이든 web이 상태를
 * 합치거나 새로 만들지는 않는다.
 */
export function representativeJobs(jobs: RunningJob[]): RunningJob[] {
  const byId = new Map<string, RunningJob>()
  for (const job of jobs) {
    const seen = byId.get(job.job_id)
    if (!seen) {
      byId.set(job.job_id, job)
      continue
    }
    const a = job.attempt ?? Number.NEGATIVE_INFINITY
    const b = seen.attempt ?? Number.NEGATIVE_INFINITY
    if (a >= b) byId.set(job.job_id, job)
  }
  return [...byId.values()]
}

export function selectScreen(view: CaseView): Screen {
  const blocking = view.notices.filter((n) => n.blocking)
  const info = view.notices.filter((n) => !n.blocking)
  const jobs = representativeJobs(view.running_jobs)
  const base = { blocking, info, jobs }

  // 음성 결과도 evidence=null이라 값만으로는 조립 전과 구분되지 않는다. 계약이
  // 구분 수단으로 정한 notice code로만 가른다(계약 B절 notices[].code, #168 [A]).
  if (view.evidence === null && view.notices.some((n) => n.code === 'evidence.visual_event_not_observed')) {
    return { ...base, kind: 'NOT_OBSERVED', reason: 'evidence=null · evidence.visual_event_not_observed' }
  }

  // 상황 응답 대기도 evidence=null이다. 진행 화면에 두면 끝나지 않으므로 notice로 가른다
  // (#232). 응답 입력(맞아요/잘 모르겠어요)은 아직 없어 notice만 보인다.
  if (view.evidence === null && view.notices.some((n) => n.code === 'case.situation_response_pending')) {
    return { ...base, kind: 'AWAIT_RESPONSE', reason: 'evidence=null · case.situation_response_pending' }
  }

  // evidence=null은 「값이 없다」가 아니라 「증거 조립 전」이다. 값 상태 화면이
  // 아니라 진행 상태 화면이 담당한다(value-state-display.md §4).
  if (view.stage === 'EVIDENCE_REVIEW' && view.evidence === null) {
    return { ...base, kind: 'PROGRESS', reason: 'stage=EVIDENCE_REVIEW · evidence 조립 전' }
  }

  switch (view.stage) {
    case 'INTAKE':
      return { ...base, kind: 'PROGRESS', reason: 'stage=INTAKE' }
    case 'SEARCHING':
      return { ...base, kind: 'PROGRESS', reason: 'stage=SEARCHING' }
    case 'CANDIDATE_REVIEW':
      // 후보 0건은 실패가 아니다 — 빈 결과 화면으로 구분해 그린다.
      // 후보가 있으면 가장 유력한 후보로 초안을 준비하는 중이다(core-user-flow.md
      // §8-1). 후보 비교는 기본 화면이 아니라 결과 화면의 「다른 후보 보기」다.
      return view.candidates.length === 0
        ? { ...base, kind: 'NO_RESULT', reason: 'stage=CANDIDATE_REVIEW · candidates 0건' }
        : { ...base, kind: 'PROGRESS', reason: `stage=CANDIDATE_REVIEW · 후보 ${view.candidates.length}건 · 초안 준비 중` }
    case 'EVIDENCE_REVIEW':
      return { ...base, kind: 'EVIDENCE', reason: 'stage=EVIDENCE_REVIEW · evidence 있음' }
    case 'READY':
      // READY는 PACKAGE_READY 파생 gate 성립 시점이다(계약 B절 §7). package가
      // 없으면 신고자료 화면을 만들 수 없으므로 증거 화면으로 남는다.
      return view.package === null
        ? { ...base, kind: 'EVIDENCE', reason: 'stage=READY · package 없음' }
        : { ...base, kind: 'HANDOFF', reason: 'stage=READY · package 있음' }
  }
}
