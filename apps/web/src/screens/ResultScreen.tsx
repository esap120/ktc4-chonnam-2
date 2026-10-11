import type { JSX } from 'react'
import { isAction, type Action, type CaseView, type InfoState } from '../contracts/caseView'
import { ACTION_LABELS, INFO_STATE_LABELS, formatValue, noticeMessage, reportFieldLabel } from '../contracts/labels'
import { StatusBadge } from '../components/StatusBadge'

// Figma 03_Main_Result 틀: 요약 → 신고용 영상(+다른 후보) → 번호판 → 신고서 초안(+어떻게 정했는지) → 동작.
// 값과 상태는 package.report_field_states를 그대로 쓴다(value-state-display.md §5-1).
// 무엇이 잘 됐든 안 됐든 결과는 여기서 알린다 — 진행 화면은 멈추지 않는다.
// 제출 단계로의 연결은 READY(= PACKAGE_READY)이고 blocking notice가 없을 때만 연다(#171 C, #172).
// 실패해도 package·evidence가 없을 수 있다(판독 실패·상황 응답 대기). 그래도 notice와
// 다시 시도는 보여야 하므로, 요약은 항상 그리고 나머지는 있는 것만 그린다.
// ponytail: 위치는 지도·검색어 복사 없이 초안 행만 둔다. 붙여넣을 칸이 아니라 직접 고른다.
// 안전신문고 칸 중 붙여넣을 수 있는 것만 복사 버튼을 둔다. 나머지는 거기서 직접 고른다(core-user-flow §21).
// 「제목」 칸은 report_fields에 아직 없다.
const PASTE = new Set(['vehicle_number', 'violation_expression'])

export function ResultScreen(props: {
  view: CaseView
  onCandidates: () => void
  onPlate: () => void
  onDetails: () => void
  onAction: (noticeCode: string, action: Action) => void
}): JSX.Element {
  const { view } = props
  const pkg = view.package
  const evidence = view.evidence

  // 요약 칩은 상태별 개수를 셀 뿐 판정하지 않는다.
  const counts = new Map<InfoState, number>()
  const fields = pkg ? Object.entries(pkg.report_fields) : []
  for (const s of Object.values(pkg?.report_field_states ?? {})) {
    counts.set(s.info_state, (counts.get(s.info_state) ?? 0) + 1)
  }
  const others = view.candidates.filter((c) => !c.selected).length
  const ready = view.stage === 'READY' && !view.notices.some((n) => n.blocking)
  const noVideo = view.notices.some((n) => n.code === 'case.report_video_not_generated')
  const pasteText = fields
    .filter(([key, value]) => PASTE.has(key) && value)
    .map(([key, value]) => `${reportFieldLabel(key)}: ${formatValue(value!)}`)
    .join('\n')

  return (
    <div className="stack">
      <h1 className="page-title">신고자료</h1>

      <section className="panel panel-p">
        <h2 className="panel-t">{ready ? '신고자료가 준비됐어요.' : '신고자료를 완성하지 못했어요.'}</h2>
        {view.notices.map((n) => (
          <div key={n.code} className={`flow-notice${n.blocking ? ' blocking' : ''}`} style={{ marginTop: 10 }}>
            {noticeMessage(n.message_key)}
            {/* notice가 실은 actions[]만 버튼으로 연다 — 계약 밖 버튼은 만들지 않는다 */}
            {n.actions.filter(isAction).map((a) => (
              <button key={a} type="button" className="btn sm notice-action" onClick={() => props.onAction(n.code, a)}>
                {ACTION_LABELS[a]}
              </button>
            ))}
          </div>
        ))}
        <div className="chips">
          {[...counts].map(([state, n]) => (
            <span key={state} className="chip">
              {INFO_STATE_LABELS[state]} {n}
            </span>
          ))}
        </div>
      </section>

      {evidence && (
        <section className="panel panel-p stack">
          <div className="video-box">
            <div className="video-main">
              {noVideo ? (
                <span>신고용 영상이 아직 없어요</span>
              ) : (
                <>
                  <span className="video-play" aria-hidden>
                    ▶
                  </span>
                  <span className="video-cap">신고용 영상 · 원본에서 사건 구간만 잘라 만든 영상이에요</span>
                </>
              )}
            </div>
            {others > 0 && (
              <button type="button" className="video-side" onClick={props.onCandidates}>
                다른 후보 영상 {others} →
              </button>
            )}
          </div>
          <div className="plate-row">
            <span className="plate-img">{evidence.plate_display.value ?? '번호판 없음'}</span>
            <span className="plate-meta">
              <b>번호판</b>
              <StatusBadge state={evidence.plate_display.info_state} />
            </span>
            <button type="button" className="btn sm" onClick={props.onPlate}>
              자세히 보기
            </button>
          </div>
        </section>
      )}

      {pkg && (
        <>
          <section className="panel panel-p">
            <div className="sec-label">
              안전신문고 신고서 초안
              <button type="button" className="link-btn" onClick={props.onDetails}>
                어떻게 정했는지 →
              </button>
            </div>
            <div className="kv kv-rows">
              {fields.map(([key, value]) => (
                <div className="kv-row draft" key={key}>
                  <span className="kv-k">{reportFieldLabel(key)}</span>
                  <span className="kv-v">
                    <span className="kv-val">{value === null ? '알 수 없음' : formatValue(value)}</span>
                  </span>
                  {/* 오른쪽은 2줄 — 위에 상태, 아래에 동작. 줄마다 폭이 달라 들쭉날쭉하지 않게 한다 */}
                  <span className="draft-side">
                    {pkg.report_field_states[key] && <StatusBadge state={pkg.report_field_states[key].info_state} />}
                    {PASTE.has(key) ? (
                    <button
                      type="button"
                      className="btn sm"
                      disabled={value === null}
                      onClick={() => value && navigator.clipboard?.writeText(formatValue(value))}
                    >
                      복사
                    </button>
                  ) : (
                    <span className="pick-hint">안전신문고에서 직접 골라요</span>
                  )}
                  </span>
                </div>
              ))}
            </div>
          </section>
    
          <div className="btnrow center">
            {pkg.capabilities.includes('COPY_FIELDS') && (
              // 전체 복사는 붙여넣을 칸만, 칸 이름을 붙여 복사한다(§21)
              <button
                type="button"
                className="btn"
                disabled={!ready || !pasteText}
                onClick={() => navigator.clipboard?.writeText(pasteText)}
              >
                붙여넣을 내용 전체 복사
              </button>
            )}
            {pkg.capabilities.includes('OPEN_DESTINATION') && (
              <button type="button" className="btn btn-blue" disabled={!ready}>
                안전신문고로 이동
              </button>
            )}
          </div>
          {!ready && <p className="kv-src center-text">위 문제가 해결돼야 안전신문고로 넘어갈 수 있어요.</p>}
      </>
      )}

      <p className="disclaimer">
        대신고는 신고를 <b>대신 접수하지 않습니다.</b> 자료를 받아 안전신문고에서 내용을 다시 확인하고 직접
        제출하셔야 합니다.
      </p>
    </div>
  )
}
