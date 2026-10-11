# [Recording] 블랙박스 GPS 실측 데이터·제조사 자료 조사

> **성격:** 외부 공식 자료와 현재 저장소를 대조한 조사 문서다. 구현 결정이나 특정
> 제조사 포맷 지원 약속이 아니다.
>
> **조사일:** 2026-10-04
>
> **범위:** 블랙박스 GPS가 제공할 수 있는 정보, 실제 원시 데이터 확보 방법,
> `recording` GPS parser와 reverse geocoder의 책임 경계

## 1. 결론

1. GPS를 지원하는 블랙박스는 전용 Viewer에서 위치·이동 경로·속도·시각 등의
   정보를 보여준다. 제조사와 모델에 따라 GPS가 내장되거나 외장 안테나/마운트로
   제공된다.
2. 제조사 설명서는 사용자가 볼 수 있는 **논리적 정보**는 설명하지만, GPS가 영상
   컨테이너의 private metadata인지, 별도 sidecar/DB인지, NMEA·GPX인지와 같은
   **원시 저장 형식**은 확인시켜 주지 않는다.
3. 따라서 현재 단계에서 NMEA·GPX 또는 특정 제조사 형식을 기본값으로 가정하면 안
   된다. GPS가 활성화된 실제 SD카드의 전체 파일 구조와 전용 Viewer 표시값을 함께
   확보한 뒤 parser adapter를 선택해야 한다.
4. GPS 부재는 정상 상태다. 현재 계약대로 `UNKNOWN +
   recording.gps.source_absent`로 표현할 수 있으며, 파싱 실패인 `ERROR`와 구분해야
   한다.
5. 좌표 추출과 주소 변환은 분리한다. `recording`은 원본에서 좌표와 provenance를
   관찰하고, reverse geocoder는 확인된 좌표를 주소로 변환하는 별도 adapter로 둔다.

## 2. 확인 수준

이 문서는 표현을 다음 세 수준으로 구분한다.

| 표기 | 의미 |
| --- | --- |
| **확인** | 저장소 코드·Mock 또는 제조사 공식 문서에서 직접 확인함 |
| **추론** | 확인된 정보로부터 가능한 해석이지만 원시 샘플로 검증하지 않음 |
| **미확정** | 실제 GPS 탑재 기기의 SD카드 원본 없이는 결정할 수 없음 |

## 3. 현재 저장소 상태

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| 공통 GPS 표현 | **확인** | `Observation<T> v1`이 `OK`, `UNKNOWN`, `ERROR`와 source/provenance를 정의한다. |
| GPS 정상 Mock | **확인** | `scenario_happy_001.json`에 `lat`, `lon`, `source.kind=recording.gps_stream`, `impl_ref=gps-parser/default`가 있다. |
| GPS 부재 Mock | **확인** | `scenario_unknown_abstain_partial_001.json`에 `UNKNOWN`, `value=null`, `recording.gps.source_absent`가 있다. |
| Evidence 소비 | **확인** | `evidence/assembly.py`가 `OK`인 GPS의 `lat`, `lon`을 `location.coord`으로 채택한다. |
| 경도 필드 이름 | **불일치** | Accepted Observation 문서의 GPS 예시는 `lng`, Mock과 Evidence 구현은 `lon`을 사용한다. GPS value subtype의 정본을 찾지 못했으므로 이 문서에서 어느 쪽도 확정하지 않는다. |
| 실제 Real E2E 연결 | **미구현** | `case/real_e2e.py`는 공개 GPS producer가 없어 `gps_observation=None`을 전달한다. |
| Recording GPS parser | **미구현** | `src/daesingo/recording`에 GPS 관찰 공개 capability와 vendor parser가 없다. |
| Reverse geocoder | **미구현** | Kakao·Naver geocoder adapter와 인증 설정이 없다. |
| 현재 실제 AVI 샘플의 GPS | **미확인** | 지금까지의 ffprobe·SD카드 조사에서 GPS stream/metadata가 확인되지 않았다. GPS 미지원 모델이라고 단정할 근거는 아니다. |

관련 저장소 자료:

- [`Observation<T> v1`](../../../architecture/contracts/contract-observation.md)
- [`scenario_happy_001.json`](../../../../data/mock/recording/scenario_happy_001.json)
- [`scenario_unknown_abstain_partial_001.json`](../../../../data/mock/recording/scenario_unknown_abstain_partial_001.json)
- [`architecture-input-memo.md`](architecture-input-memo.md)

## 4. 제조사 공식 자료에서 확인되는 정보

| 제조사·예시 | GPS 장치 | 공식 자료에서 확인되는 사용자 수준 정보 | 원시 저장 형식 |
| --- | --- | --- | --- |
| IROAD | 모델별 내장 또는 외장 GPS | 속도와 위치를 기록하며, Viewer에서 경로·속도·지도 정보를 확인할 수 있다. 일부 설명서는 위치와 주행속도 제공을 명시한다. | **미확정** |
| THINKWARE U3000 | 내장 GPS | 기기가 속도·시각 데이터를 추적하고, PC Viewer가 속도·위치·시각 정보를 표시한다. | **미확정** |
| VIOFO | 모델에 따라 GPS mount 또는 본체 통합 | GPS logger가 속도·위도·고도를 기록하고 시각을 동기화한다. Player는 GPS 경로·속도와 G-sensor를 표시한다. | **미확정** |
| BlackVue GPS-1 호환 모델 | 외장 GPS receiver | 속도·위치 정보를 녹화물에 통합하고 Viewer에서 경로를 지도와 동기화한다. | **미확정** |

공식 출처:

- [IROAD FAQ — GPS 연결 시 속도와 위치 데이터 기록](https://iroad.kr/support/help-faq/)
- [IROAD 다운로드 — 모델별 설명서와 Viewer](https://iroad.kr/ko/download/)
- [IROAD NX1 설명서 — 외장 GPS, 위치·주행속도·Google Map](https://iroad.kr/download/Manual/IROAD_NX1_Manual_EN.pdf)
- [THINKWARE PC Viewer — 속도·위치·시각 표시](https://support.thinkware.com/hc/en-us/articles/6987549044115-How-to-Install-the-PC-Viewer)
- [THINKWARE U3000 — 내장 GPS와 속도·시각 추적](https://thinkware.com/global/product/u3000)
- [VIOFO GPS 안내 — 속도·위도·고도 기록과 시각 동기화](https://support.viofo.com/support/solutions/articles/19000088199-do-viofo-dashcams-support-gps-tracking-)
- [VIOFO Player — GPS 경로·속도와 G-sensor 표시](https://www.viofo.com/pages/viofo-app)
- [BlackVue GPS-1 — 속도·위치 통합과 지도 재생](https://blackvue.com/products/external-gps-receiver)

### 해석 시 주의사항

- **확인:** 위 자료는 GPS로 위치·속도·경로 등을 제공한다는 사실을 뒷받침한다.
- **미확정:** 문서의 “녹화물에 통합” 또는 Viewer 표시만으로 MP4/AVI 표준 stream,
  private container box/chunk, sidecar 파일, 별도 DB 중 어느 방식인지 알 수 없다.
- **미확정:** 좌표계, 샘플링 주기, 정밀도, GPS fix 상태, 결측 표현, 영상 PTS와 GPS
  timestamp의 정렬 규칙은 모델별 실제 샘플이 필요하다.
- G-sensor는 Viewer에서 GPS와 함께 표시될 수 있지만 가속도 센서 데이터다. GPS
  좌표와 같은 source로 합치지 않는다.

## 5. 예상되는 논리 데이터와 현재 계약의 차이

제조사 문서로 예상할 수 있는 논리 레코드는 다음과 같다. 이는 **권장 내부 후보
모델**이지 실측된 원시 schema가 아니다.

| 필드 후보 | 필요성 | 확인 상태 |
| --- | --- | --- |
| `observed_at` 또는 source offset | 영상 Timeline과 좌표를 연결 | 필요성은 확인, 실제 표현 미확정 |
| `latitude`, `longitude` | Canonical GPS 좌표 | 제조사 기능으로 확인 |
| `speed`와 단위 | Viewer·영상 overlay에 사용 | 여러 제조사에서 확인 |
| `altitude` | 모델별 선택 정보 | VIOFO 공식 자료에서 확인 |
| `heading`/direction | 모델별 선택 정보 | IROAD 계열 설명 자료에서 확인되나 공통 보장 아님 |
| `fix_status`, satellite/accuracy | 좌표 신뢰성 판단 | 설명서만으로 보장 여부 미확정 |
| source file/stream provenance | 재현과 오류 추적 | 프로젝트에서 필요, 제조사 형식 미확정 |

현재 `Observation<{lat, lon}>`은 사건 위치 좌표 한 건을 Evidence에 전달하기에는
충분하지만, 이동 경로 전체·속도·고도·샘플 시각을 표현하는 계약은 아니다. 실제
샘플을 얻기 전에는 공통 Contract를 확장하지 않는다. parser 내부에서 track point를
읽더라도 사건 시점의 좌표를 어떤 규칙으로 선택할지는 별도 검증이 필요하다.

또한 현재 Accepted Observation 문서의 예시는 `lng`, 실행 Mock과 Evidence 코드는
`lon`을 사용한다. parser 구현 전에 GPS value subtype의 경도 필드 이름과 기존
Consumer 영향 범위를 Contract Owner와 확인해야 한다.

## 6. 실제 실측 데이터 확보 요건

영상 파일만 복사하면 sidecar/DB를 놓칠 수 있으므로 다음 묶음을 요청한다.

| 필수 자료 | 이유 |
| --- | --- |
| 정확한 제조사·모델·펌웨어 버전 | 동일 제조사도 모델/펌웨어별 저장 형식이 달라질 수 있음 |
| GPS 내장/외장 여부와 촬영 당시 GPS fix 상태 | GPS 부재와 수신 실패를 구분 |
| SD카드의 전체 폴더 구조 | 영상 밖 sidecar·DB·index 파일 탐색 |
| 연속 영상 2~3개와 주변의 모든 비영상 파일 | 파일 경계에서 GPS 연속성과 timestamp 정렬 확인 |
| 전용 Viewer의 동일 구간 화면 | 좌표·속도·경로·시각의 비교 기준 확보 |
| 짧고 알려진 이동 구간과 촬영 시각 | parser 결과의 위치·시간 sanity check |

개인정보 보호를 위해 자택·직장 등 민감한 출발지/도착지는 피하고, 외부 공유본에는
정밀 좌표·차량번호·로컬 경로를 남기지 않는다. 원본은 read-only로 조사하고
SHA-256·크기·mtime을 전후 비교한다.

### 실측 조사 순서

1. 원본을 수정하거나 Viewer로 내보내기 전에 SD카드 전체 파일 목록과 fingerprint를
   기록한다.
2. `ffprobe`로 영상·audio·data/subtitle stream, format/stream tags와 side data를
   확인한다. ffprobe에서 안 보인다는 이유만으로 GPS가 없다고 단정하지 않는다.
3. 영상과 같은 basename, 생성시각 또는 directory에 있는 sidecar·DB·index 파일을
   식별한다.
4. 제조사 Viewer에서 한 시각의 위치·속도·경로를 캡처하고 원본 timestamp와
   비교한다.
5. 원시 파일을 hex/text/SQLite 등 **식별 단계**에서만 확인한다. 포맷을 모른 채
   값을 보정하거나 제조사 파일을 수정하지 않는다.
6. 최소 두 지점 이상을 Viewer 값과 parser 후보 결과로 대조한다.
7. 파일 경계, GPS 미수신 구간, 터널/지하, 잘못된 timestamp를 별도 실패 사례로
   보존한다.

## 7. Parser 책임 경계 제안

다음은 현재 계약에 맞춘 **후속 구현 제안**이며 아직 구현 결정이 아니다.

```text
ExternalSource bundle
  → vendor/format detector
  → GPS parser adapter
  → timestamp/Timeline alignment validation
  → Observation<{lat, lon}>
  → Evidence

Observation<{lat, lon}>
  → reverse geocoder adapter
  → 주소/행정구역 후보
```

| 상황 | 권장 Observation | 비고 |
| --- | --- | --- |
| GPS source가 실제로 없음 | `UNKNOWN`, `value=null`, `recording.gps.source_absent` | 정상적인 부분 상태 |
| 지원하지 않는 vendor 형식 | `UNKNOWN` 또는 별도 지원 상태 필요 | 실제 Consumer 요구 확인 후 결정 |
| source는 있으나 파싱 작업 실패 | `ERROR`, `value=null`, namespaced reason | 부재와 구분 |
| 좌표 범위·시각 정렬 검증 통과 | `OK`, `{lat, lon}` | `source.ref`와 근거 ref 필요 |
| 좌표는 있으나 정렬/신뢰가 불충분 | `NEEDS_REVIEW` 검토 | 값을 실어도 되는지 Consumer 합의 필요 |

필수 검증 후보:

- 위도 `[-90, 90]`, 경도 `[-180, 180]` 범위
- NaN·무한대·빈 좌표 거부
- 좌표계 확인과 WGS84 변환 provenance
- GPS timestamp 또는 source offset의 단조 증가
- Recording Timeline 범위와의 정렬
- 결측 구간과 GPS fix 상실을 값 보간으로 숨기지 않음
- source asset·sidecar·parser implementation 식별자 보존

## 8. Reverse geocoder 조사

> **후속 결정 (2026-10-05):** MVP provider는 Kakao Local REST API로 확정했다.
> 인증·실패 정책과 미구현 범위는
> [`gps-reverse-geocoder-provider.md`](../decisions/gps-reverse-geocoder-provider.md)를 따른다.

좌표 파싱과 주소 변환은 실패 원인과 외부 의존성이 다르므로 분리한다.

| 후보 | 공식 기능 | 인증 | 현재 상태 |
| --- | --- | --- | --- |
| Kakao Local REST API | WGS84 경도(`x`)·위도(`y`)를 행정구역 또는 지번/도로명 주소로 변환 | REST API 키 | 구현·키 설정 없음 |
| NAVER Cloud Maps Reverse Geocoding | WGS84 등 좌표를 행정동·법정동·지번·도로명 주소로 변환 | NCP API key ID/secret | 구현·키 설정 없음 |

공식 출처:

- [Kakao 지도 REST API — 좌표로 행정구역/주소 변환](https://developers.kakao.com/docs/ko/kakaomap/rest-api)
- [NAVER Cloud Maps — Reverse Geocoding](https://api.ncloud-docs.com/docs/ai-naver-mapsreversegeocoding-gc)

API 제공 여부만 확인했으며, 요금·쿼터·개인정보 처리·서비스 약관·정확도 비교는 이
문서에서 결정하지 않는다. API 정책은 변경될 수 있으므로 실제 도입 시 공식 문서를
다시 확인해야 한다.

## 9. Edge case 목록

| 구분 | 사례 | 기대 처리 방향 |
| --- | --- | --- |
| 장치 | GPS 미장착·외장 GPS 분리 | `UNKNOWN/source_absent` |
| 수신 | 터널·지하·도심 음영으로 fix 상실 | 결측 보존, 임의 좌표 생성 금지 |
| 포맷 | ffprobe에 GPS stream이 보이지 않음 | sidecar/private metadata 추가 조사 |
| 포맷 | vendor/firmware별 schema 차이 | adapter 격리, 포맷 추측 금지 |
| 시간 | GPS UTC와 영상 local time/timezone 불일치 | timezone·anchor 근거 없이는 절대시각 확정 금지 |
| 시간 | 분할파일 경계의 중복·gap | Recording Timeline에 맞춰 검증 |
| 값 | `(0, 0)`, 범위 밖 좌표, NaN | 유효 좌표로 채택하지 않음 |
| 값 | 속도 단위 km/h·mph·knots 불명 | 단위 근거와 함께 정규화 |
| 좌표계 | WGS84가 아닌 제조사 좌표 | 좌표계 확인 전 geocoder 호출 금지 |
| 정렬 | GPS sample 주기와 video frame 주기 차이 | 선택/보간 정책을 명시하고 provenance 보존 |
| 외부 API | timeout·quota·인증 실패 | 좌표 관찰은 유지하고 주소 변환 실패를 분리 |
| 개인정보 | 로그·리포트에 정밀 경로 노출 | 최소 좌표만 전달하고 원시 경로/키 비노출 |

## 10. 다음 Gate

| Gate | 완료 증거 |
| --- | --- |
| G1. GPS 실측 원본 확보 | 모델·펌웨어·GPS 장치 상태, SD카드 전체 구조, Viewer 화면 |
| G2. 원시 저장 위치 식별 | container/private data/sidecar/DB 중 실제 위치와 fingerprint |
| G3. 최소 parser spike | 두 지점 이상에서 Viewer의 시각·좌표·속도와 일치 |
| G4. Timeline 정렬 검증 | 파일 경계와 GPS 결측을 포함한 source offset 매핑 결과 |
| G5. Canonical 출력 검증 | 경도 필드 이름 합의, `OK/UNKNOWN/ERROR` fixture와 Evidence 연결 테스트 |
| G6. Geocoder 결정 | provider 정책·키 관리·실패 fallback·개인정보 범위 합의 |

G1·G2 전에는 GPS parser 라이브러리나 vendor schema를 확정하지 않는다. 실제 데이터가
없는 상태에서는 현재 `Observation<T>` 경계와 adapter 구조만 유지하는 것이 안전하다.
