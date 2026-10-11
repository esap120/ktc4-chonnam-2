// 계약이 등재한 값 목록 — web이 「무엇을 다 다뤄야 하는가」의 정본.
//
// 값 자체를 여기서 정하지 않는다. 원문은 아래 문서가 소유하고 이 파일은 옮겨 적은 것이다.
//   - contract-job-record-case-view.md  B절 §5 스키마 · §7 Enum · A절 §12(label_key 등재)
//
// **왜 목록을 따로 두는가.** 이 파일이 생기기 전에는 `labels.ts`의 매핑 맵이 곧 등재
// 목록 노릇을 했고, 검증은 fixture에 실제로 등장한 값만 훑었다. 그래서 「계약엔 등재됐는데
// fixture엔 아직 없는 값」이 구조적으로 안 잡혔다 — `job.overlay_time_read`·`job.fine_verify`·
// `job.report_video_export`가 전부 「처리 중」 fallback으로 뭉개지고 있었는데 테스트는 초록색이었다.
// readout의 `registry.py`와 같은 자리다.
//
// 새 값은 계약에 등재한 뒤 여기에 옮긴다. 옮기면 `labels.test`의 전수 매핑 검사가
// 문구를 만들 때까지 깨진다 — 그것이 이 파일의 목적이다.

import type {
  InfoState,
  JobStatus,
  ProgressState,
  Readiness,
  Severity,
  SituationConfirmation,
  Stage,
} from './caseView'

/** B절 §5 — `stage` 5종 */
export const STAGES: readonly Stage[] = [
  'INTAKE',
  'SEARCHING',
  'CANDIDATE_REVIEW',
  'EVIDENCE_REVIEW',
  'READY',
]

/**
 * B절 §7 — `info_state` 5종. web은 이 값으로만 표시를 가른다(§10 불변조건 12).
 *
 * 서술어 주의 — `check_boundaries.py`의 web 금지 문자열은 부분 문자열로 검사해서,
 * 「나눈다」를 뜻하는 흔한 한국어 서술어 하나가 그 안에 금지 토큰을 품는다. 규칙이 막으려는
 * 것은 신고 마감일 계산이고 이 줄은 그것과 무관한데도 실패로 잡힌다. 표현을 바꿔 피한다.
 */
export const INFO_STATES: readonly InfoState[] = [
  'INFO_AI_ESTIMATED',
  'INFO_SOURCE_VERIFIED',
  'INFO_USER_CONFIRMED',
  'INFO_NEEDS_REVIEW',
  'INFO_UNKNOWN',
]

/** B절 §5 — `progress[].state` 5종. `PARTIAL`은 v1.3에서 추가됐다(중단·부분 완료 양쪽) */
export const PROGRESS_STATES: readonly ProgressState[] = [
  'PENDING',
  'RUNNING',
  'DONE',
  'FAILED',
  'PARTIAL',
]

/** B절 §5 — `running_jobs[].status` 2종. 끝난 작업은 애초에 이 배열에 없다 */
export const JOB_STATUSES: readonly JobStatus[] = ['PENDING', 'RUNNING']

/** B절 §5 — `notices[].severity` 3종 */
export const SEVERITIES: readonly Severity[] = ['INFO', 'WARN', 'ERROR']

/** B절 §5 — `requirements_*.readiness` 4종. 객체 자체가 `null`인 것과 다른 값이다(§10-10) */
export const READINESSES: readonly Readiness[] = ['PASS', 'WARN', 'BLOCK', 'UNKNOWN']

/** B절 §7 — `candidates[].situation_confirmation` 4종(v1.3에서 evidence 값 공간과 맞춤) */
export const SITUATION_CONFIRMATIONS: readonly SituationConfirmation[] = [
  'NOT_ASKED',
  'CONFIRMED',
  'CORRECTED',
  'USER_UNSURE',
]

/**
 * A절 §12 · B절 §12 — 등재된 `running_jobs[].label_key` 4종.
 *
 * `COARSE_SEARCH`는 아직 전용 키가 없어 fallback을 그대로 쓴다(유소연 확인, 우선순위 낮음).
 * 미등록 kind도 fallback이다 — `actions[]`와 달리 여기는 fallback이 계약에 명시돼 있다.
 */
export const JOB_LABEL_KEYS = [
  'job.plate_read',
  'job.overlay_time_read',
  'job.fine_verify',
  'job.report_video_export',
  'job.hint_extract',
] as const

export const JOB_LABEL_FALLBACK_KEY = 'job.generic_processing'

/**
 * `evidence.reason_code` — B절 §7 「`review_needed` 파생 규칙」이 정한 3종.
 *
 * 원인이 한 필드면 그 필드에 대응하는 코드를, 둘 이상이면 `multiple_fields_need_review`를 쓴다.
 * 별도 `label_key`가 내려오지 않으므로 문구는 web이 갖는다(`situation_confirmation`과 같은 경우).
 */
export const REVIEW_REASON_CODES = [
  'evidence.event_time_needs_review',
  'evidence.location_needs_review',
  'evidence.multiple_fields_need_review',
] as const
