// 표시 키 → 화면 문구.
//
// 규칙(value-state-display.md §3-2): web은 label_key로 문구를 고르고
// source.kind 문자열을 직접 해석하지 않는다. 미등록 키는 지어내지 않고
// fallback 문구를 쓴다 — 단 actions[]만은 fallback 없이 버튼을 렌더하지
// 않는다(계약 B절 §7).

import type { Action, InfoState, ProgressState, Readiness, SituationConfirmation } from './caseView'
import { JOB_LABEL_FALLBACK_KEY } from './registry'

/** 값의 출처 — `*_display.source_label_key` (v5 fixture 실측 9종) */
const SOURCE_LABELS: Record<string, string> = {
  'plate.source.plate_ocr': '번호판 판독',
  'time.source.filename': '파일명',
  'time.source.filename_time': '파일명 시각',
  'time.source.overlay_ocr': '영상 화면 시각',
  'time.source.user_correction': '사용자 정정',
  'location.source.user_hint': '사용자가 말한 위치',
  'event.source.visual_inference': '영상 분석',
  'event.source.category_mapping': '분류 매핑',
  'event.source.violation_expression': 'AI 작성 위반 문장',
}

/** 미등록 키 fallback — 계약이 `running_jobs[].label_key`에 정한 것과 같은 패턴 */
export const SOURCE_FALLBACK = '출처 확인 중'

export function sourceLabel(key: string | null): string | null {
  if (key === null) return null
  return SOURCE_LABELS[key] ?? SOURCE_FALLBACK
}

/**
 * 진행 중 작업 — `running_jobs[].label_key` (A절 §12 등재 4종 + fallback).
 *
 * v5 fixture에는 `job.plate_read`와 fallback 둘만 등장하지만 계약은 넷을 등재했다. fixture에
 * 있는 것만 채우면 나머지가 「처리 중」으로 뭉개진다 — 특히 `job.report_video_export`는
 * 「신고용 영상 만들기」를 누른 직후 뜨는 작업이라 무엇을 눌렀는지가 화면에서 사라진다.
 */
const JOB_LABELS: Record<string, string> = {
  'job.generic_processing': '처리 중',
  'job.plate_read': '번호판 판독 중',
  'job.overlay_time_read': '화면 시각 판독 중',
  'job.hint_extract': '상황 설명을 읽는 중',
  'job.fine_verify': '정밀 확인 중',
  'job.report_video_export': '신고용 영상 만드는 중',
}

export function jobLabel(key: string): string {
  return JOB_LABELS[key] ?? JOB_LABELS[JOB_LABEL_FALLBACK_KEY]
}

/**
 * 신고요건·자료완성 판정 — `requirements_*.readiness` 4종.
 *
 * 등재값을 그대로 화면에 내보내지 않는다. 세 gate는 각각 구분해 표시하되(§3-5) 값은 문구로
 * 바꾼다 — 한 패널에서 `PASS`와 「완료」가 나란히 뜨던 자리다.
 * 객체 자체가 `null`인 것은 「아직 판정 안 함」이라 별도 문구다(§10-10 — 사용자 수정 직후
 * 재검사 전이면 `null`이 정상이다).
 */
const READINESS_LABELS: Record<Readiness, string> = {
  PASS: '충족',
  WARN: '확인 필요',
  BLOCK: '충족 못함',
  UNKNOWN: '알 수 없음',
}

export const READINESS_NOT_CHECKED = '확인 전'

export function readinessLabel(readiness: Readiness | null | undefined): string {
  if (readiness === null || readiness === undefined) return READINESS_NOT_CHECKED
  return READINESS_LABELS[readiness] ?? READINESS_NOT_CHECKED
}

/**
 * 「확인이 필요한 값이 있다」의 원인 — `evidence.reason_code` 3종(B절 §7 파생 규칙).
 *
 * 이 코드는 `label_key`가 아니라 원인 코드라 문구가 같이 내려오지 않는다. 그렇다고 raw를
 * 화면에 내보내면 사용자가 `evidence.location_needs_review`를 읽게 된다 — `message_key`·
 * `source_label_key`를 전부 매핑해 놓고 여기만 예외일 이유가 없다.
 */
const REVIEW_REASON_MESSAGES: Record<string, string> = {
  'evidence.event_time_needs_review': '발생 시각을 확인해 주세요.',
  'evidence.location_needs_review': '발생 장소를 확인해 주세요.',
  'evidence.multiple_fields_need_review': '확인이 필요한 값이 여러 건 있습니다.',
}

export const REVIEW_REASON_FALLBACK = '확인이 필요한 값이 있습니다.'

export function reviewReason(code: string | null): string {
  if (code === null) return REVIEW_REASON_FALLBACK
  return REVIEW_REASON_MESSAGES[code] ?? REVIEW_REASON_FALLBACK
}

/** 안내 문구 — `notices[].message_key` (v5 fixture 실측 13종 + 계약 등재 2종).
 *
 * 마지막 2종은 fixture에 아직 안 나온다. 아래 테스트가 fixture에 있는 키만
 * 훑으므로 이 항목은 검사에 안 걸린다 — 키 문자열은 계약에서 그대로 옮긴다
 * (`contract-job-record-case-view.md` §`notices[].code`, 2026-09-14 등재). */
const NOTICE_MESSAGES: Record<string, string> = {
  'notice.event_time_needs_review': '사건 시각을 확인해 주세요.',
  'notice.time_conflict': '시각 단서가 서로 달라 확인이 필요합니다.',
  'notice.post_stamp_required': '촬영 후 찍힌 시각이라 확인이 필요합니다.',
  'notice.time_post_stamp_required': '촬영 후 찍힌 시각이라 확인이 필요합니다.',
  'notice.overlay_not_present': '영상에 시각 표시가 없습니다.',
  'notice.overlay_presence_undetermined': '영상에 시각 표시가 있는지 확인하지 못했습니다.',
  'notice.overlay_ocr_failed': '영상의 시각 표시를 읽지 못했습니다.',
  'notice.plate_abstained': '번호판을 확정하지 못했습니다.',
  'notice.plate_read_failed_retry_exhausted': '번호판 판독에 실패했습니다.',
  'notice.plate_read_cancelled': '번호판 판독이 중단됐습니다.',
  'notice.search_no_candidates': '조건에 맞는 장면을 찾지 못했습니다.',
  // #197 — 탐색 Run 실패. 「후보 없음」과 다른 시스템 실패다.
  'notice.candidate_search_failed': '장면을 찾는 중에 문제가 생겼어요.',
  'notice.visual_event_unconfirmed': '어떤 상황인지 아직 확인되지 않았습니다.',
  // #168 [A] — 가장 유력한 후보에서 위반이 관찰되지 않은 음성 결과.
  'notice.visual_event_not_observed': '이 장면에서는 신고할 위반을 확인하지 못했어요.',
  'notice.report_video_not_generated': '신고용 영상이 아직 만들어지지 않았습니다.',
  // 이슈 #48 확정 — 문구 뜻은 계약이 정했다(「지도에 붙여넣을 검색어를 제공하지
  // 못한다, 기억나는 장소를 직접 검색해야 한다」). 발동 기준은 `location` 부재가
  // 아니라 `location_display.search_keyword == null`이다.
  'notice.location_search_keyword_missing':
    '지도에 붙여넣을 검색어를 만들지 못했습니다. 기억나는 장소로 직접 검색해 주세요.',
  // #171 C-2 — 상황 응답 전이라 Package가 나가지 않은 상태. 응답 버튼은 이
  // notice의 action이 아니라 #106 command로 연다.
  'notice.situation_response_pending': '신고 상황을 확인해 주시면 신고자료를 준비하겠습니다.',
}

// ISO 시각(`2026-08-24T18:05:12+09:00`)을 `2026-08-24 18:05:12`로 보여준다. 포맷만 web이
// 한다(value-state-display.md §3-4) — 시각이 아닌 값은 그대로 돌려준다.
export function formatValue(value: string): string {
  return value.replace(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/, '$1 $2')
}

export const NOTICE_FALLBACK = '확인이 필요한 항목이 있습니다.'

export function noticeMessage(key: string): string {
  return NOTICE_MESSAGES[key] ?? NOTICE_FALLBACK
}

/** 버튼 — 닫힌 7종. 미등록 값은 렌더하지 않으므로 fallback을 두지 않는다. */
export const ACTION_LABELS: Record<Action, string> = {
  EDIT_EVENT_TIME: '시각 직접 입력',
  MANUAL_PLATE_INPUT: '번호판 직접 입력',
  GENERATE_REPORT_VIDEO: '신고용 영상 만들기',
  REVIEW_TIME: '시각 확인하기',
  RETRY_PLATE_READ: '번호판 다시 읽기',
  EDIT_HINT: '설명 고치기',
  RETRY_SEARCH: '다시 찾기',
}

/** 과거 timeline revision 기준 후보 — `candidates[].stale_revision_label_key` */
const STALE_LABELS: Record<string, string> = {
  'candidate.stale_timeline_revision': '이전 기준으로 찾은 장면',
}

export const STALE_FALLBACK = '이전 기준'

export function staleLabel(key: string | null): string | null {
  if (key === null) return null
  return STALE_LABELS[key] ?? STALE_FALLBACK
}

/**
 * 후보 시각의 출처 — `candidates[].at_provenance_label_key`
 * (`case-view/v1.4` §7 등재 3종, 2026-09-14 유소연·신유민 합의).
 *
 * raw `at_provenance`(`recording.filename_time` 등)를 web이 직접 해석하지
 * 않는다. `event_time_display.source_label_key`와 문구가 겹쳐 보여도 다른
 * 값이다 — 「후보의 시각을 어떻게 구했나」와 「확정 시각의 출처」는 별개
 * 질문이고, fixture에서 한쪽만 바뀌는 사례가 실제로 있다
 * (`correction_rerun` rev2→rev3).
 */
const AT_PROVENANCE_LABELS: Record<string, string> = {
  'candidate.at_provenance.filename_time': '파일명 시각',
  'candidate.at_provenance.overlay_ocr': '영상 화면 시각',
  'candidate.at_provenance.timeline_relative_only': '영상 안 위치만 확인',
}

/**
 * 미등록 raw(case가 `label_key=null`로 내림)와 web이 모르는 키를 같은 문구로
 * 합친다 — 계약 §10-14가 두 케이스를 나누지 않기로 했다.
 */
export const AT_PROVENANCE_FALLBACK = '시각 출처 확인 중'

export function atProvenanceLabel(key: string | null | undefined): string {
  if (key === null || key === undefined) return AT_PROVENANCE_FALLBACK
  return AT_PROVENANCE_LABELS[key] ?? AT_PROVENANCE_FALLBACK
}

/**
 * 상황 확인 — 닫힌 4종이고 label_key가 내려오지 않아 web이 문구를 갖는다
 * (value-state-display.md §5-3). NOT_ASKED와 USER_UNSURE를 같은 빈칸으로
 * 합치지 않는 것이 이 필드가 생긴 이유다.
 */
export const SITUATION_LABELS: Record<SituationConfirmation, string> = {
  NOT_ASKED: '아직 확인하지 않음',
  CONFIRMED: '사용자 확인됨',
  CORRECTED: '사용자가 고침',
  USER_UNSURE: '모르겠다고 답함',
}

/** 정보 상태 5종 — `core-user-flow.md` §3-1 이름을 그대로 쓴다 */
export const INFO_STATE_LABELS: Record<InfoState, string> = {
  INFO_USER_CONFIRMED: '사용자 확인됨',
  INFO_SOURCE_VERIFIED: '출처 확인됨',
  INFO_AI_ESTIMATED: 'AI 추정',
  INFO_NEEDS_REVIEW: '확인 필요',
  INFO_UNKNOWN: '알 수 없음',
}

const STEP_LABELS: Record<string, string> = {
  file_intake: '영상 등록',
  coarse_search: '장면 찾기',
  candidate_review: '후보 확인',
  plate_read: '번호판 판독',
  overlay_time_read: '화면 시각 판독',
  evidence_assembly: '증거 정리',
  requirement_check: '신고요건 확인',
  package_assembly: '신고자료 만들기',
}

export function stepLabel(step: string): string {
  return STEP_LABELS[step] ?? step
}

export const PROGRESS_LABELS: Record<ProgressState, string> = {
  PENDING: '대기',
  RUNNING: '진행 중',
  DONE: '완료',
  FAILED: '실패',
  PARTIAL: '부분 완료',
}

const REPORT_FIELD_LABELS: Record<string, string> = {
  safety_report_type: '신고 유형',
  occurred_at: '발생 시각',
  location: '발생 장소',
  vehicle_number: '차량 번호',
  violation_expression: '위반 내용',
}

export function reportFieldLabel(key: string): string {
  return REPORT_FIELD_LABELS[key] ?? key
}

/**
 * 모든 맵이 아는 키의 합집합. 계약에 새 `*_label_key`가 생기면(예: v1.4의
 * `at_provenance_label_key`) 그 값이 여기에 없어 테스트가 먼저 깨진다 —
 * 화면에 fallback 문구가 조용히 뜨는 것을 막는 자리다.
 */
export const KNOWN_LABEL_KEYS: ReadonlySet<string> = new Set([
  ...Object.keys(SOURCE_LABELS),
  ...Object.keys(JOB_LABELS),
  ...Object.keys(STALE_LABELS),
  ...Object.keys(AT_PROVENANCE_LABELS),
])
