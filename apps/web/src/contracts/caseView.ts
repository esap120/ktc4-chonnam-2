// CaseView — `contract-job-record-case-view.md` B절 §5·§6·§7 (case-view/v1.3)
//
// 이 파일이 web의 타입 정본이다. `apps/prototype/src/types.ts`의 CaseState는
// 참고만 하고 가져오지 않는다(`docs/modules/web/decisions/web-stack.md`).
// web이 읽는 계약은 CaseView 하나뿐이며 evidence·search·readout 계약을 직접
// 읽지 않는다.

export type Stage = 'INTAKE' | 'SEARCHING' | 'CANDIDATE_REVIEW' | 'EVIDENCE_REVIEW' | 'READY'

export type InfoState =
  | 'INFO_AI_ESTIMATED'
  | 'INFO_SOURCE_VERIFIED'
  | 'INFO_USER_CONFIRMED'
  | 'INFO_NEEDS_REVIEW'
  | 'INFO_UNKNOWN'

export type ProgressState = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'PARTIAL'
export type JobStatus = 'PENDING' | 'RUNNING'
export type Readiness = 'PASS' | 'WARN' | 'BLOCK' | 'UNKNOWN'
export type Severity = 'INFO' | 'WARN' | 'ERROR'
export type SituationConfirmation = 'NOT_ASKED' | 'CONFIRMED' | 'CORRECTED' | 'USER_UNSURE'

// §7 — 닫힌 7종. 미등록 값은 버튼을 렌더하지 않는다(fallback 없음).
export const ACTIONS = [
  'EDIT_EVENT_TIME',
  'MANUAL_PLATE_INPUT',
  'GENERATE_REPORT_VIDEO',
  'REVIEW_TIME',
  'RETRY_PLATE_READ',
  'EDIT_HINT',
  'RETRY_SEARCH',
] as const
export type Action = (typeof ACTIONS)[number]

export interface ValueDisplay {
  value: string | null
  needs_review: boolean
  info_state: InfoState
  source_label_key: string | null
}

export interface LocationDisplay extends ValueDisplay {
  coord: { lat: number; lon: number } | null
  search_keyword: string | null
}

export interface CodeDisplay {
  code: string | null
  label: string | null
  needs_review: boolean
  info_state: InfoState
  source_label_key: string | null
}

export interface EvidenceView {
  record_id: string
  case_type_display: CodeDisplay
  report_type_display: CodeDisplay
  violation_display: CodeDisplay
  plate_display: ValueDisplay
  event_time_display: ValueDisplay
  location_display: LocationDisplay
  user_edited: boolean
  preview_ref: string | null
  review_needed: boolean
  reason_code: string | null
}

export interface FieldState {
  info_state: InfoState
  source_label_key: string | null
}

export interface PackageView {
  package_ref: string | null
  report_fields: Record<string, string | null>
  report_field_states: Record<string, FieldState>
  unconfirmed_fields: string[]
  artifact_ref: string | null
  capabilities: string[]
  warnings: string[]
}

export interface Candidate {
  candidate_id: string
  at: string | null
  at_provenance: string
  /**
   * `case-view/v1.4` 신규(§7). raw `at_provenance`가 authoritative이고 이 키는
   * case가 골라 주는 표시용 파생값이다 — web은 raw를 해석하지 않고 이 키로만
   * 문구를 고른다. 매핑 안 되는 raw는 case가 `null`로 내린다(§10-14).
   * 계약상 필드는 항상 존재하지만(Y) **v5 fixture는 아직 안 내린다** — 그래서
   * `undefined`를 받을 수 있고, `null`과 같게 다룬다(둘 다 fallback 문구).
   */
  at_provenance_label_key?: string | null
  /** case가 매긴 후보 순위(1부터, #122; 계약상 int|null). 배열은 rank 오름차순. mock fixture는 아직 안 내린다. */
  rank?: number | null
  /**
   * 후보의 시간축 위치(ms, #184). `null`이면 마커를 그리지 않고 stale 배지만 둔다.
   * mock fixture는 아직 안 내린다.
   */
  marker_ms?: number | null
  observed: string
  thumb_ref: string | null
  selected: boolean
  timeline_revision: number
  stale_revision: boolean
  stale_revision_label_key: string | null
  situation_confirmation: SituationConfirmation
}

export interface Notice {
  code: string
  severity: Severity
  blocking: boolean
  message_key: string
  actions: string[]
}

export interface RunningJob {
  job_id: string
  kind: string
  label_key: string
  status: JobStatus
  attempt?: number
}

export interface Requirements {
  readiness: Readiness
  checks: unknown[]
}

export interface CaseView {
  case_id: string
  case_rev: number
  stage: Stage
  user_reviewed: boolean
  manifest_summary: {
    file_count: number
    ok_file_count: number
    failed_file_count: number
    duration_sec: number
    range: [string, string] | null
  }
  hints: { time: string | null; vehicle: string | null; situation: string | null; location: string | null }
  progress: { step: string; state: ProgressState }[]
  candidates: Candidate[]
  evidence: EvidenceView | null
  requirements_evidence: Requirements | null
  requirements_package: Requirements | null
  package: PackageView | null
  running_jobs: RunningJob[]
  notices: Notice[]
}

export function isAction(value: string): value is Action {
  return (ACTIONS as readonly string[]).includes(value)
}
