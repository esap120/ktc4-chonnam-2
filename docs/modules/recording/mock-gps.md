# Mock GPS 조회 경계

`RecordingService.from_fixture(fixture)`는 기존 recording Mock JSON의
`gps_observations`를 검증하고 복사해 등록한다. 실제 영상의 GPS를 읽거나 새로운 좌표를
생성하지 않는다. 공개 조회는 `list_gps_observations() -> list[GPSObservation]`이다.
`GPSObservation.value`는 `GPSCoordinate | None`이며 `lat`, `lon`을 사용한다.

```python
fixture = load_recording_fixture("scenario_happy_001")
recording = RecordingService.from_fixture(fixture)
observations = recording.list_gps_observations()
payloads = [item.model_dump(exclude_unset=True) for item in observations]
```

기존 두 GPS fixture의 값·상태·source·support_refs·producer·reason을 보존한다.
필드가 없는 기존 다섯 fixture는 `[]`다. 명시적인 UNKNOWN 관찰값은 삭제하거나
새로 생성하지 않으며 `value=null`, `recording.gps.source_absent`를 그대로 제공한다.
새 service에서 관찰값이 없다는 사실은 GPS source가 없다는 관찰 결과가 아니다.

좌표의 유한성·범위, 상태별 value 규칙, OK의 source ref 및 fixture MediaStream 소속을
검증한다. NEEDS_REVIEW는 공통 Observation 규칙에 따라 tentative 값 또는 null을 허용한다.
동일 typed payload 중복은 거부한다. Observation global ID나 source별 최신값 정책은
새로 만들지 않으며 서로 다른 관찰값을 덮어쓰지 않는다. GPS 추가 필드는 조용히 버리지 않는다.
fixture 등록과 repository 등록에서 재검증하고, 입력 및 반환 객체는 깊은 복사로 분리한다.
list 순서는 fixture 순서를 보존할 뿐 시간 순서나 최신 관찰 선택을 뜻하지 않는다.

## 미결 계약·Consumer 접합 사항

- `contract-observation.md`의 GPS 예시는 `lng`지만 현재 Mock과 Evidence assembly는
  `lon`을 사용한다. 이번 구현은 `lon`을 유지하고 `lng` alias/자동 변환을 추가하지 않는다.
  Canonical 철자 통일은 별도 Owner 합의가 필요하며 이번 변경에서 계약을 수정하지 않는다.
- Evidence의 현재 경로는 non-OK이면 null을 요구하지만 공통 Observation은
  NEEDS_REVIEW의 tentative 값을 허용한다. 현재 두 Mock(OK/UNKNOWN)은 호환되며,
  tentative GPS의 소비 정책은 별도 합의가 필요하다. 다른 Owner 코드는 수정하지 않는다.
- source별 필터, Timeline 구간 GPS, 실제 parser/vendor adapter, 역지오코딩,
  Real E2E 배선·GPS 재실행 lifecycle은 포함하지 않는다.
