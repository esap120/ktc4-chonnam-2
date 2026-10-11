import type { JSX } from 'react'
import type { CaseView } from '../contracts/caseView'
import { Panel } from '../components/Panel'
import { SituationInput } from './UploadScreen'

// 후보 0건은 실패가 아니다. candidates=[]·evidence=null·package=null을
// 실패 화면으로 그리지 않는다(체크리스트 Failure/Partial · scenario_empty_001).
export function NoResultScreen(props: { view: CaseView }): JSX.Element {
  const { hints, manifest_summary } = props.view
  return (
    <Panel title="말씀하신 장면을 찾지 못했어요">
      <div className="kv-src">영상은 잘 받았어요. 설명을 조금 바꿔 주시면 다시 찾아볼게요.</div>
      <div className="kv kv-rows">
        <div className="kv-row">
          <span className="kv-k">등록된 영상</span>
          <span className="kv-v">
            <span className="kv-val mono">
              {manifest_summary.ok_file_count} / {manifest_summary.file_count}
            </span>
          </span>
        </div>
        {hints.situation && (
          <div className="kv-row">
            <span className="kv-k">말한 상황</span>
            <span className="kv-v">
              <span className="kv-val">{hints.situation}</span>
            </span>
          </div>
        )}
        {hints.time && (
          <div className="kv-row">
            <span className="kv-k">말한 시각</span>
            <span className="kv-v">
              <span className="kv-val">{hints.time}</span>
            </span>
          </div>
        )}
      </div>
    </Panel>
  )
}

// 결과 없음의 출구(와이어프레임 12 「기억 단서 고치기」). 단서를 다시 글로 받아 새 탐색을
// 시작한다 — 홈과 같은 입력 방식이라 사용자가 새로 배울 것이 없다. 조건별 「넓히기」
// 버튼은 단서를 항목으로 나누는 창구(#210)와 범위 확대 비용 표시(§22)가 생기면 붙인다.
export function RetrySearch(props: {
  situation: string
  onSituation: (text: string) => void
  onRetry: () => void
}): JSX.Element {
  return (
    <Panel title="어떤 장면이었는지 조금만 더 알려 주세요">
      <div className="stack">
        <span className="kv-src">시간이나 차 색깔, 어떤 일이 있었는지를 떠오르는 대로 적어 주세요. 처음과 조금만 달라도 다른 장면을 찾을 수 있어요.</span>
        <SituationInput
          label="다시 찾을 상황"
          example="아침 7시쯤이었던 것 같아요. 검은 승용차가 중앙선을 넘어 제 쪽으로 들어왔어요."
          rows={3}
          value={props.situation}
          onChange={props.onSituation}
        />
        <span className="kv-src">Tab 키를 누르면 예시 문장이 들어가요.</span>
        <button type="button" className="btn pri cta" onClick={props.onRetry}>
          다시 찾기
        </button>
      </div>
    </Panel>
  )
}
