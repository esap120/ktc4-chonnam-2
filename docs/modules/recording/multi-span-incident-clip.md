# 다중 span IncidentClip Baseline

기존 공개 호출 `build_incident_clip(resolution)`로 여러 원본의 연속 구간을 생성한다.
호출자는 Timeline revision과 명시적 VIDEO ref로 해소한 SpanResolution을 전달한다.
Contract/API를 추가하지 않는다.

다중 원본은 COMPLETE이며 spans 배열의 sequence가 0부터 연속 증가하고 Timeline
구간이 그 순서대로 이어져야 한다. 배열을 자동 정렬하거나 sequence를 재부여하지 않는다.
중복 SourceAsset, gap, overlap, 모순된 순서, 원본 변경·소실은
`INCIDENT_CLIP_BUILD_FAILED`로 거부한다. 현재 revision의 매핑을 다시 조회한다.
기존 단일 원본의 경계 밖 PARTIAL 처리와 fixture 동작은 유지한다.

각 구간은 IncidentClip 내부 encoding 설정으로 strict 인코딩하고 검증된 MP4들을
연결한다. Search용 AnalysisSource best-effort는 중첩 호출에서도 비활성화한다.
각 encode와 concat의 `-xerror`를 유지하며 최종 출력도 전체 strict decode한다.
packet 폐기, 오류 무시, 새 timestamp 보정, gap 압축, frame 복제는 하지 않는다.
기존 상대 원점 변환 및 decimal seam 비교 규칙은 공용 연결 엔진과 동일하다.

원본 AssetSpan 전체, Timeline revision과 요청 범위는 source_provenance에 보존한다.
media_stream_refs는 사용한 span 순서다. duration·byte_size는 실제 출력에서 측정하고,
timeline_range는 관측 frame coverage의 시작·끝이다. 동일 provenance·생성 조건·실제 bytes·
관측 범위에 대해서만 기존 opaque clip ref를 재사용하며 기존 clip은 변경하지 않는다.
Readout은 기존 source provenance 기반 resolve_frame/read_frame 경로를 사용한다.

범위는 source-local start 0 placement로 해소되는 연속 단일 카메라 체인이다.
카메라 역할·파일 순서·촬영 연속성은 추론하지 않는다. 연결 출력은 동일한 time base와
해상도여야 한다. 전체 구간 bytes를 메모리에 보관하는 기존 방식의 한계가 있다.
다른 geometry 정규화, 자동 overlap 처리, 신고영상 export는 포함하지 않는다.

검증: `python -m pytest tests/recording/test_multi_span_incident_clip.py -q`
합성 2·3원본 frame 순서·provenance·ref 재사용·실패와 cleanup을 검사한다.
실제 AVI 실험 배치는 촬영 gap/overlap 또는 절대 연속성을 증명하지 않는다.
