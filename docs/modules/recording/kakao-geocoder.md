# Kakao reverse geocoder adapter

`recording.kakao_geocoder`는 provider 내부 adapter다. RecordingService capability,
Canonical Contract, 기존 GPS Observation은 변경하지 않는다. 최종 Owner·composition
root 배선과 Case/Evidence 표시 주소 선택은 별도 합의 대상이다.

```python
from daesingo.recording.kakao_geocoder import KakaoReverseGeocoder

# composition root가 획득한 값으로 주입한다. 여기서 환경 파일/Secret을 읽지 않는다.
geocoder = KakaoReverseGeocoder(api_key=injected_key, timeout_sec=injected_timeout)
result = geocoder.reverse_geocode(validated_gps_observation)
```

검증된 OK GPS만 WGS84로 요청한다. 입력 GPS는 재검증하며 lon → x, lat → y로
매핑한다. timeout은 필수 양수·유한 입력이며 socket 작업 timeout이다. 전체 실행
deadline이나 재시도 수치를 확정하지 않는다. retry/cache/TTL/provider fallback은 없다.

기본 의존성에는 공용 HTTP client가 없다. lock의 httpx/requests는 optional dependency
경로에 있으므로 이를 필수 설치로 가정하지 않는다. 표준 라이브러리 HTTPSConnection을
사용해 추가 dependency 없이 TLS 검증을 수행하며 redirect는 따라가지 않는다.
성공·실패·timeout에서 연결을 닫는다.

`KakaoGeocoderResult`는 내부 결과이며 status는 OK/SKIPPED/FAILED다. `address`(지번)와
`road_address`(도로명)를 별도 보존한다. 각 주소의 `address_name`과 문자열 상세 필드는
immutable 값으로 보존하며 어느 주소도 최종 표시값으로 선택하지 않는다. 도로명 주소가
없어도 지번 주소가 유효하면 OK다. 전체 응답 원문은 결과에 포함하지 않는다.

| 내부 failure | 의미 |
| --- | --- |
| INVALID_INPUT | Observation·좌표 검증 실패, 호출 없음 |
| GPS_NOT_OK | 유효한 non-OK Observation, SKIPPED·호출 없음 |
| TIMEOUT | 연결·읽기 timeout |
| AUTHENTICATION | HTTP 401/403 인증·권한 거부 |
| RATE_LIMIT | HTTP 429 quota/rate limit |
| SERVER_ERROR | HTTP 5xx |
| HTTP_ERROR | 그 외 비정상 HTTP status, redirect 포함 |
| TRANSPORT_ERROR | 연결/TLS/HTTP transport 실패 |
| INVALID_JSON | JSON·문자 인코딩 파싱 실패 |
| INVALID_SCHEMA | 응답 shape/type/count 불일치 또는 유효한 주소 없음 |
| EMPTY_RESULT | documents=[] 및 total_count=0 |

이 이름들은 **공개 failure taxonomy가 아니다**. HTTP 오류 body는 해석·보관하지 않으며
오류 응답 문구로 주소를 추정하지 않는다. 어떤 실패도 원래 GPS를 변경하지 않는다.

adapter는 로그를 출력하지 않는다. 키·좌표·응답·원본 예외를 결과에 포함하지 않으며
adapter/result/address의 repr도 민감한 값을 출력하지 않는다. Consumer와 composition
root 역시 입력 Observation, 주소 details, HTTP 요청/메모리 dump를 로그에 남기지 않아야 한다.

검증은 fake HTTPS connection을 통한 무네트워크 테스트다. 실제 키 등록·API 호출은
수행하지 않았다. 따라서 provider 결정 문서의 실제 좌표 1건 검증·배포 Secret 주입 Gate는
완료로 간주하지 않는다. 실제 GPS의 좌표계/출처 신뢰성 검증도 adapter의 역할이 아니다.

참조: [provider 결정](decisions/gps-reverse-geocoder-provider.md),
[Runtime 주입 경계](../../runtime/runtime-tech-spec.md#151-module--provider-configuration-주입-경계),
[Kakao 공식 규격](https://developers.kakao.com/docs/ko/local/dev-guide#coord-to-address)
(2026-10-05 확인).
