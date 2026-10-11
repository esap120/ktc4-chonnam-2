# GPS reverse geocoder provider 결정

> **상태:** Accepted
>
> **결정일:** 2026-10-05
>
> **범위:** GPS 좌표를 주소 후보로 변환할 때 사용할 MVP provider 선택

## 결정

MVP의 GPS reverse geocoder provider는 **Kakao Local REST API**로 통일한다.

- 호출 API: `GET https://dapi.kakao.com/v2/local/geo/coord2address.json`
- 입력 좌표계: `WGS84`
- 입력 매핑: GPS 경도 `lon`을 `x`, 위도 `lat`을 `y`로 전달한다.
- 인증: 서버 측에서 REST API 키를 사용한다. 키를 코드·로그·리포트·클라이언트에
  포함하지 않는다.
- MVP에서 NAVER 등 다른 provider로 자동 fallback하지 않는다.

공식 API 규격과 쿼터·운영 정책은 변경될 수 있으므로 실제 adapter 구현 및 배포 전에
Kakao 공식 문서를 다시 확인한다.

- [Kakao 지도 REST API](https://developers.kakao.com/docs/ko/kakaomap/rest-api)
- [Kakao API 호출 쿼터](https://developers.kakao.com/docs/ko/getting-started/quota)

## 책임 경계

```text
Recording GPS parser
  -> 검증된 Observation<{lat, lon}>
  -> Kakao reverse geocoder adapter
  -> 주소 후보
  -> Consumer의 표시·채택 정책
```

이 결정은 provider만 확정한다. 다음 사항은 확정하거나 변경하지 않는다.

- GPS 원시 데이터 parser와 제조사별 포맷
- Canonical Contract와 기존 `Observation` 구조
- geocoder adapter의 최종 Owner와 composition root
- 주소 결과를 저장·표시할 Case/Evidence 필드와 우선순위
- timeout, retry, cache TTL, rate-limit 수치
- 실제 API 키 발급·Secret 등록·배포 환경 설정

## 실패 정책

| 상황 | 처리 |
| --- | --- |
| GPS가 없거나 좌표 상태가 `OK`가 아님 | Kakao를 호출하지 않는다. |
| 좌표 범위 또는 좌표계가 확인되지 않음 | 호출하지 않고 기존 GPS 상태와 근거를 유지한다. |
| 인증 실패, timeout, quota 초과, 서버 오류 | 좌표 Observation을 삭제하거나 주소를 추정하지 않는다. 주소 변환 실패로 분리한다. |
| 응답에 도로명 주소가 없음 | 실패로 단정하지 않는다. 실제 응답을 보존하고 표시·채택 규칙은 Consumer 합의 후 정한다. |
| 빈 결과 | 가짜 주소를 만들거나 다른 provider로 자동 전환하지 않는다. |

외부 로그와 Benchmark에는 REST API 키, 전체 응답 원문, 불필요한 정밀 좌표를 남기지
않는다.

## 구현 Gate

Kakao 연동이 완료됐다고 판단하려면 다음 증거가 모두 필요하다.

1. 서버 측 Secret에서 REST API 키를 읽는 adapter가 있다.
2. 검증된 `OK` 좌표만 Kakao에 전달하는 테스트가 있다.
3. 정상 응답과 인증 실패·timeout·quota 초과·빈 결과를 재현하는 테스트가 있다.
4. GPS 좌표 관찰과 주소 변환 실패가 서로 독립적으로 보존된다.
5. 실제 좌표 1건으로 재현 방법과 개인정보 비노출 여부를 확인한다.

현재 저장소는 provider 선택까지만 완료했으며, 위 구현 Gate는 아직 완료되지 않았다.
