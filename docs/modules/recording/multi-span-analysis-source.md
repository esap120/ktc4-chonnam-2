# 다중 span AnalysisSource Baseline

기존 `prepare_analysis_source(span, profile_ref, timeline_ref=...)`와
`open_analysis_source(ref)`는 유지한다. 다중 원본에는 다음 공개 capability를 사용한다.

```python
resolution = recording.resolve_span(
    timeline_ref, requested_range,
    media_stream_refs=explicit_video_refs,
)
prepared = recording.prepare_analysis_source_from_resolution(resolution, profile_ref)
opened = recording.open_analysis_source(prepared.analysis_source_ref)
with opened.stream as stream:
    content = stream.read()
```

`prepare_analysis_source_from_resolution(resolution: SpanResolution | dict,
profile_ref: str) -> AnalysisSource`는 COMPLETE인 연속 구간만 받는다.
배열 순서는 sequence로 정렬하지만 sequence를 새로 부여하지 않는다.
sequence가 Timeline 순서와 모순되거나 원본이 중복되면 입력 오류다.
현재 원본의 상태와 고정된 Timeline revision의 매핑도 다시 검증한다.
PARTIAL/FAILED, 변경·소실된 원본은 기존 machine-readable 오류로 거부한다.

각 원본의 선택 구간을 기존 profile로 인코딩하고, 검증된 임시 MP4들을
Timeline 순서로 연결한다. 모든 원본은 읽기만 하며 연결 전후 fingerprint를 검사한다.
임시 파일은 성공·실패·timeout에서 정리한다. 각 구간의 실제 frame coverage,
연결 출력의 VIDEO 구성·해상도·frame 수·상대 PTS·duration·faststart·bytes를 검증한다.
원본 전체의 snapshot/probe는 안전성 검사를 위해 실행할 수 있지만, 출력에는 선택한
구간의 VIDEO만 넣는다. AUDIO/subtitle은 포함하지 않는다.

실제 frame 경계는 아래 표현 오차 비교 한도 안에서 이어져야 한다. gap/overlap을 시간 압축,
frame 복제 또는 padding으로 보정하지 않는다. 바깥 시작·끝은 기존 단일 span과
같이 frame 선택 결과에 따라 달라질 수 있으며 실제 Timeline 범위를 반환한다.
MP4 duration metadata의 기존 반올림 허용 범위도 유지한다.

### 경계 비교 정밀도

Canonical 시간은 초 단위 숫자이며 내부 `TimeRange`/placement는 float다.
계약은 소수 자릿수나 1µs 정밀도를 지정하지 않는다. ffprobe의 관측 duration
`60.033333`과 rational frame 끝 `1801/30` 사이에는 약 0.333333µs 표현 차이가 있다.
독립적인 소수 6자리 반올림 경계의 차이를 다루기 위해, 내부 비교 한도를
`min(1µs, 관측 time-base tick / 2, 관측 최소 frame 길이 / 2)`로 제한한다.
이는 Canonical 정밀도나 일반 gap 허용 정책이 아니다.
입력 SpanResolution/placement의 논리적 연속성 검사는 기존처럼 정확한 일치를 요구한다.
이 한도는 해당 검사를 통과한 materialized 구간들의 관측 경계 비교에만 적용한다.

seam 각각과 전체 coverage/Timeline 길이 비교에 같은 상한을 적용하며 상한을
seam 개수만큼 늘리지 않는다. 1µs 초과 gap/overlap, 한 tick, 한 frame은 거부한다.
입력 timestamp·Timeline 범위·frame 목록은 반올림하거나 이동하지 않는다.
단일 frame coverage 검증과 출력 PTS/duration 검증의 기존 규칙은 변경하지 않는다.

Canonical 필드 추가 없이 직접 부모를 `source_refs[]`, 선택 VIDEO를
`media_stream_refs[]`, 좌표를 `timeline_ref`와 실제 `timeline_range`에 보존한다.
AnalysisSource에는 IncidentClip의 `source_provenance` 필드를 추가하지 않는다.
`duration_sec`과 `byte_size`는 최종 출력에서 측정한다. 같은 실행의 동일 요청은
현재 원본 상태를 재확인한 후 기존 ref/bytes를 재사용한다.

현재 연결은 같은 출력 time base·해상도에 한정한다. 서로 다른 geometry의 정규화,
자동 overlap, source-local trim 모델 확장, 기본 VIDEO 선택, IncidentClip stitching은
포함하지 않는다. 메모리에 구간 bytes와 최종 bytes를 보관하므로 장시간 영상의 메모리
최적화도 후속이다. 기존 trace는 개별 materialization을 기록하며 연결 전용 schema를 추가하지 않는다.

## 검증

```powershell
.venv/Scripts/python.exe -m pytest tests/recording/test_multi_span_analysis_source.py -q -p no:cacheprovider
```

합성 3원본의 색상/frame 순서, 2원본 부분 요청, 입력 배열 역순, provenance,
원본 불변, 오류와 cleanup을 검증한다. 실제 영상 opt-in에는 실행자가
`DAESINGO_RECORDING_PAIR_A`, `DAESINGO_RECORDING_PAIR_B`, 그리고
`DAESINGO_RECORDING_CHAIN_PLACEMENTS`(각 원본의 `[start,end]` JSON 배열)를 지정한다.
`test_opt_in_tail_only_real_pair_analysis`는 #252에서 합의한 후행 패턴 pair의
AnalysisSource 공개 경로를 검증한다. VIDEO ordinal 0은 실행자가 명시한다.
이 배치는 실험 좌표이며 실제 촬영 overlap이나 절대 연속성을 증명하지 않는다.
합성 2개·3개 원본의 성공 검증과 손상 입력 거부 검증도 유지한다.

## Search용 제한적 best-effort (#252)

[Recording 결정과 Search 동의](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/252)에
따라 단일·다중 AnalysisSource 공개 호출 범위에서만 후행 오류 재시도를 허용한다.
공용 엔진의 기본 동작 및 IncidentClip은 strict다. IncidentClip은 중첩 호출에서도
허용 범위를 명시적으로 비활성화한다. 공개 Contract/API와 profile 정책은 바꾸지 않는다.

먼저 기존 strict encode를 실행한다. 알려진 start-code/decoder packet 제출 오류로
실패한 경우에만 아래 근거를 독립적으로 조회한다. timeout·일반 encode 실패는 재시도하지 않는다.

- 명시적으로 선택된 VIDEO ordinal 0, AVI/H.264, B-frame 없음
- 원본 coverage의 연속성 및 기존 inspection과 재조회 frame PTS의 일치
- decoded frame과 packet의 위치·크기·PTS 일대일 대응
- packet PTS가 없으면 B-frame 없음이 확인된 경우에만 실제 DTS와 frame PTS 대조
- 대응 frame이 없는 packet은 모두 16-byte이며 선언된 RIFF 영역 밖, 마지막 decoded frame 뒤
- 오류 후보 뒤 추가 decoded frame, 중간 누락, 위치 미관측, 관측된 오류 flag는 거부

위 조건을 통과한 재시도에만 `-xerror`를 제외한다. `discardcorrupt`, packet 삭제,
새 timestamp 보정은 하지 않는다. 기존 구간 선택과 출력 상대 원점 변환은 동일하다.
실패한 임시 출력은 먼저 제거한다. 재시도 출력은 frame 수·상대 PTS·개별 duration의
정확한 일치 및 전체 strict decode를 요구한다. 해당 구간을 포함한 연결 출력에도
정확한 frame 시각 대조와 전체 strict decode를 적용한다. MP4 format duration의
기존 millisecond 직렬화 오차 허용과 Timeline seam 비교 규칙은 유지한다.

`decode_error_flags` 미출력을 0으로 간주하지 않는다. 이 정책은 #252의 제한된
후행 오류 후보 근거에 따른 best-effort이며, decoder concealment가 전혀 없다는 보증이 아니다.
원본 해상도의 무손실 framehash는 조사 근거일 뿐 480p/CRF23 runtime 비교에 쓰지 않는다.
하나라도 flag 필드가 없으면 내부 로그에 `decode_error_flags_observed=false`를 기록한다.
필드가 존재하면서 non-zero인 frame은 거부한다. 모든 packet의 byte 범위는 양수 길이이며
겹침·역전이 없어야 하고, tail은 마지막 frame 대응 packet의 끝 이후에 시작해야 한다.

내부 `daesingo.recording.analysis_tail` INFO 로그에는 best-effort 성공 여부,
strict 실패 단계, coverage/tail/output/decode/fingerprint/cleanup 검증 결과를 기록한다.
미실행 출력 검증은 null이다. 경로·파일명·명령·stderr·예외 원문은 포함하지 않는다.
기존 benchmark/trace schema를 변경하지 않는다. 실패 결과와 불완전 bytes는 저장하지 않는다.

현재 근거는 AVI의 좁은 후행 패턴에 한정한다. 다른 container·B-frame·후행 packet 크기,
ffprobe 위치 누락 등은 보수적으로 거부한다. 재조회와 strict 출력 decode 비용이 추가된다.
일반 카메라 역할 판별, 후방 분석, 증거 자산 정책, 영속 캐시 및 TTL은 범위 밖이다.
