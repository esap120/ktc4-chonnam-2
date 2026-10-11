import { useState, type JSX } from 'react'

const EXAMPLE = '6시 반쯤 미금역 근처에서 흰색 SUV가 실선을 넘어 제 앞으로 끼어들었어요.'

export type UploadState = 'idle' | 'uploading' | 'done' | 'fail'

const DROP_TEXT: Record<UploadState, string> = {
  idle: '여기에 영상 파일을 끌어다 놓으세요',
  uploading: '올리는 중',
  done: '올리기 완료',
  fail: '업로드 실패',
}

// Figma 01_Home_Upload · 01_Uploading · 01_UploadComplete · 01_UploadFail.
// 네 프레임은 같은 틀이고 끌어다 놓는 영역만 상태에 따라 바뀐다.
export function UploadScreen(props: {
  state: UploadState
  files: File[]
  /** 열 수 없어 건너뛴 파일. 일부 실패를 전체 실패로 만들지 않는다(core-user-flow §23) */
  skipped: string[]
  situation: string
  onFiles: (files: File[]) => void
  onSituation: (text: string) => void
  onSearch: () => void
}): JSX.Element {
  const [over, setOver] = useState(false)
  const pick = (files: FileList | null) => {
    if (files?.length) props.onFiles([...files])
  }

  return (
    <div className="stack">
      <div>
        <h1 className="page-title">블랙박스 영상을 올려주세요</h1>
        <p className="kv-src">
          신호위반 · 중앙선 침범 · 진로변경 · 이륜차 안전모 미착용 장면을 찾아 드려요.
          <br />
          찾은 장면은 신고할 가능성이 있는 후보예요. 제출 전에 꼭 직접 확인해 주세요.
        </p>
      </div>
      <label
        className={`dropzone dz-${props.state}${over ? ' over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          pick(e.dataTransfer.files)
        }}
      >
        {props.state !== 'idle' && <span className={`dz-ring dz-ring-${props.state}`} aria-hidden />}
        <b>{DROP_TEXT[props.state]}</b>
        {props.state === 'idle' && <span className="kv-src">여러 파일도 한 번에 올릴 수 있어요. 촬영 시각 정보도 확인해요.</span>}
        {props.files.length > 0 && <span className="kv-src">{props.files.map((f) => f.name).join(', ')}</span>}
        {/* 원인(형식·손상·네트워크)을 단정하지 않는다 — 화면은 알 수 없다(#224 recording 리뷰) */}
        {props.state === 'fail' && <span className="kv-src">파일을 올리지 못했어요. 다시 골라 주세요.</span>}
        {(props.state === 'idle' || props.state === 'fail') && (
          <span className="btn sm pri">{props.state === 'fail' ? '다시 선택' : '파일 선택'}</span>
        )}
        <input type="file" accept="video/*" multiple hidden onChange={(e) => pick(e.target.files)} />
      </label>
      {props.state === 'done' && props.skipped.length > 0 && (
        <p className="skip-list">
          올리지 못했거나 열 수 없는 파일 {props.skipped.length}개는 건너뛰었어요: {props.skipped.join(', ')}. 나머지
          영상으로 찾아볼게요.
        </p>
      )}
      <SituationInput
        label="어떤 상황이었나요?"
        example={EXAMPLE}
        rows={4}
        value={props.situation}
        onChange={props.onSituation}
      />
      <p className="kv-src hint">Tab 키를 누르면 예시 문장이 들어가요. 비워 두셔도 영상에서 찾아볼게요.</p>
      <button type="button" className="btn pri cta" disabled={props.state !== 'done'} onClick={props.onSearch}>
        영상에서 찾아보기
      </button>
    </div>
  )
}

// 상황 설명 입력칸. 비어 있을 때만 Tab이 예시를 채운다 — 글이 있으면 원래 Tab(다음 칸으로 이동)이다.
export function SituationInput(props: {
  label: string
  example: string
  rows: number
  value: string
  onChange: (text: string) => void
}): JSX.Element {
  return (
    <textarea
      className="field situation"
      rows={props.rows}
      aria-label={props.label}
      placeholder={`예: ${props.example}`}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Tab' && !e.shiftKey && !props.value) {
          e.preventDefault()
          props.onChange(props.example)
        }
      }}
    />
  )
}
