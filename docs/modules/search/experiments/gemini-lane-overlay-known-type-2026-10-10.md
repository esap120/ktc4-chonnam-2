# Gemini 사건 종류 지정 + 차선 표시 영상 비교

2026-10-10. 교량 실선 변경 개발 영상 1개, 조건당 3회. **원본만 제공한 경우와 원본·차선 표시본을 함께 제공한 경우 모두 0/3 검출이었다.** 성공한 API 응답 6개 모두 `NOT_OBSERVED`다. 차선 표시본 추가에 따른 개선은 이 사례에서 확인되지 않았다.

## 입력과 비교 조건

- 원본: `src/daesingo/search/video/20260620_141927_EVT_1.avi`, 시작부터 20초.
- 두 조건 모두 사건 종류 `SOLID_LINE_LANE_CHANGE`만 제공했다. 정답 차량, 정답 사건 구간, 위반 발생 사실은 프롬프트에 넣지 않았다.
- A 조건: 원본 관측 영상 1개. B 조건: 같은 원본 관측 영상 + PP-LiteSeg 표시 영상, 각각 별도 영상 파트.
- 원본과 표시본은 동일한 40개 소스 프레임을 사용한다. 원본 2fps, 1280×720. 실제 모델 반환명 `gemini-3.8-flash`, 추론 강도 `low`.
- 기존 프록시는 영상 재생 1초당 한 프레임으로 샘플링하므로, 각 원본 관측을 재생 1초씩 유지하는 40초 입력으로 준비했다. 원본 기준 0.5초 간격이다. 재생 30fps 컨테이너의 반복 프레임은 추가 관측이 아니다.
- JSON 응답은 입력 재생 시각을 요청하고 숫자 시각에 0.5를 곱해 원본 시각으로 저장했다. API 영상의 음성은 두 조건 모두 제외했다.
- 공통 검증 프롬프트와 JSON 스키마를 사용했다. 입력 영상 안내만 실제 제공된 영상 수에 맞게 달리했다. 실행 순서는 A/B, B/A, A/B다.
- 초록=모델 실선, 분홍=모델 점선, 노랑=모델 황색 이중선. 표시 색과 실제 페인트 색을 구분하도록 명시했다. 모델이 제공하지 않는 페인트 색·단일/이중 정보는 UNKNOWN이며 원본에서 확인하도록 요청했다. 차량 ID나 차량 추적 표시는 넣지 않았다.

PP-LiteSeg 출력은 [앞선 차선 구분 실험](pp-liteseg-solid-dashed-2026-10-10.md)의 2fps 예측을 재사용했다. 별도의 실선/점선 보정이나 정답을 이용한 마스크 수정은 하지 않았다.

## 결과

| 조건 | OBSERVED | NOT_OBSERVED | UNCERTAIN | 입력 토큰 합계 | 출력 토큰 합계 | 평균 API 지연 |
|---|---:|---:|---:|---:|---:|---:|
| 원본만 | 0/3 | 3/3 | 0/3 | 11,010 | 1,231 | 9.09초 |
| 원본 + 표시본 | 0/3 | 3/3 | 0/3 | 18,969 | 1,351 | 12.47초 |

성공한 6호출의 총 토큰은 **32,561**이다. 표시본 추가 시 입력 토큰은 약 **1.72배**였다. 금액은 검증된 프록시 요율을 적용하지 않아 산출하지 않았다. 위 지연은 미디어 준비 시간을 제외한다.

원본 조건 3회는 모두 차량들이 자기 차로를 유지한다고 답했고 `target_vehicle`는 null이었다. 표시본 조건도 같은 차로 유지로 판단했다. 한 응답은 흰색 SUV와 회색 SUV를 함께 지칭했고, 다른 2회는 대상이 null이었다. 표시본 조건 2회는 경계를 점선이라고 기록했다. 일부 근거에는 교량의 실선 구간을 인지하면서도 전방 SUV의 차로 변경은 부정했다.

따라서 이 결과를 단순히 실선 인식 실패 하나로 설명할 수 없다. **차량과 동일한 경계의 전후 위치 관계를 읽는 데 실패한 것이 가능한 설명**이며 원인 확정은 아니다. 실선·점선 마스크만 추가해도 시간에 따른 횡단 인식이 해결된다는 가설은 이번 조건에서 지지되지 않았다.

## 원본 대조와 검증

실제로 보낸 MP4에서 원본 시각 4·6·8·10초에 해당하는 프레임을 디코딩해 `api-input-review.jpg`로 대조했다. 짙은 SUV는 4·6초에 안쪽 차선 경계 왼쪽, 8초에 경계 위, 10초에 오른쪽에 보인다. 촬영 차량의 움직임도 함께 있다. 기존 정답의 실선 변경 사건에 대해 모든 응답이 차로 변경 자체를 부정하므로 미검출로 기록했다. 이 대조는 정밀 차량·경계 궤적 GT를 새로 만든 작업은 아니다.

두 API 영상 모두 40초, 1280×720, 영상 1,200프레임이며 음성 스트림이 없다. 전체 디코딩 오류가 없고, 80개 관측을 원본 JPEG와 대조한 최대 평균 절대 픽셀 오차는 1.233이었다. 각 조건 3회, 반환 모델, JSON 스키마, 숫자 시각 환산을 확인했다. 실행 스크립트 컴파일·LSP 오류 검사와 programming 규칙 검사도 통과했다.

최초 요청과 오류 재현 요청은 출력 예산 4,096토큰 때문에 HTTP 400으로 거절됐다. 서버가 명시한 일반 응답 한도 2,000에 맞춘 뒤 6호출이 모두 성공했다. 거절된 요청은 위 판정·토큰 통계에서 제외했고 기록을 따로 보존했다. 거절 요청의 토큰 사용량은 반환되지 않았다.

## 해석 범위

- 이미 확인한 양성 개발 영상 1개다. 일반 검출률이나 다른 영상의 성능을 뜻하지 않으며 오탐률을 측정하지 않았다.
- 이전 실험과 모델 해상도·프롬프트·시간 범위가 다르므로 과거 결과와 직접적인 성능 비교는 하지 않는다. 이번 A/B 안에서만 표시본의 추가 효과를 비교한다.
- 표시본에는 실선·점선 혼합 예측과 구조물 오탐이 있다. 특히 10초 경계의 일부는 분홍색으로 칠해져 있다. 모델 표시를 차선 정답으로 취급할 수 없다.
- 표시본 상단의 `t=`는 원본 시각이고 API 재생 시각은 두 배다. 이 두 시각이 함께 보이는 한계가 있다. 숫자 JSON 시각만 환산했으며 관찰 문장 안의 시각 언급은 원문 그대로 보존했다. 이번에는 교차 시각을 반환한 응답이 없어 교차 시각 정확도는 평가할 수 없다.
- 표시본이 실제로 관측됐다는 근거는 추가 입력 토큰과 B의 초록색 표시를 언급한 응답이다. 내부 프레임 선택 전체를 관측한 것은 아니다.

다음 실험에서는 동일 차량 ID·검사할 경계 ID와 차선 대비 위치의 변화량을 함께 제공하는 조건이 필요하다. 원본만 본 대조군과 합법 점선 변경 대조 영상도 포함해야 효과와 오탐을 함께 평가할 수 있다. 이는 이번에 실행한 결과가 아니라 후속 비교 제안이다.

## 로컬 산출물

루트: `C:/Users/User/orca/ktc4-chonnam-2/.omc/gemini-lane-overlay-2026-10-10/`

- `results.jsonl`: 6호출의 입력 재생 시각 응답과 원본 시각 응답.
- `1-raw-completion.json` 등 6개 `*-completion.json`: 실제 모델 응답 원문과 usage.
- `summary.json`, `verification.json`: 결과 집계와 검토 기록.
- `prompt-common.txt`, `prompt-raw.txt`, `prompt-raw_overlay.txt`, `response-schema.json`: 실제 입력 프롬프트와 스키마.
- `request-manifest.json`, `media-manifest.json`, `media-audit.json`: 모델·조건·해시·소스 프레임·디코딩 감사.
- `A-api-half-speed.mp4`, `B-api-half-speed.mp4`, `api-input-review.jpg`: 실제 API 입력과 시간별 대조 이미지.
- `run.py`, `inference.log`, `rejected-results.jsonl`, `transport-error.txt`: 실행과 거절 요청 기록. 키와 endpoint는 산출물에 저장하지 않았다.

제품 코드는 변경하지 않았다.

## 최초 비교의 실제 프롬프트·스키마

두 조건은 아래 입력 안내만 바꾸고 공통 본문과 스키마를 재사용했다. 이후 사용자가 제거한 페인트 색·단일/이중 필드는 이 최초 조건에만 존재한다.

```text
[입력 영상]
A 조건: 영상 A: 원본의 동일 간격 관측. 영상 B는 제공되지 않습니다.
B 조건: 영상 A: 원본의 동일 간격 관측. 영상 B: A와 같은 시간축에 차선 모델 예측을 표시한 영상.
```

공통 본문:

```text
당신의 작업은 블랙박스 영상에서 ‘실선 차로 변경’ 사건을 검증하는 것입니다.

[사전에 제공된 정보]
- 검증할 사건 종류: SOLID_LINE_LANE_CHANGE
- 사건 종류만 주어진 것입니다. 대상 차량, 발생 시각, 차선 경계는 직접 확인하세요.
- 사건 종류가 주어졌다는 이유로 영상에서 사건이 확인된다고 가정하지 마세요.

[시간축]
- 원본 클립 범위는 시작부터 20초이며 관측은 0.5초 간격입니다.
- API 입력은 이 관측들을 0.5배속으로 재생하는 40초 영상입니다.
- 입력 재생 시각 1초는 원본 0.5초입니다. 반복되는 화면은 새로운 관측이 아닙니다.
- 반환 JSON의 모든 시각은 입력 재생 기준 0~40초로 답하세요. 호출자가 0.5를 곱해 원본 시각으로 환산합니다.
- 여러 영상이 제공되면 각각 동일한 0~40초 시간축을 사용하며 시각을 이어 붙이지 마세요.

[차선 표시와 속성 정보 — 영상 B가 제공된 경우에만 적용]
표시 색은 시각화를 위한 색이며, 실제 도로 페인트 색과 다릅니다.
1. 초록색 표시: 모델 예측 실선; 실제 페인트 색 UNKNOWN; 단일선/이중선 UNKNOWN.
2. 분홍색 표시: 모델 예측 점선; 실제 페인트 색 UNKNOWN; 단일선/이중선 UNKNOWN.
3. 노란색 표시: 모델 예측 황색 이중선; 실제 페인트 색 추정 황색; 구성 추정 이중선.
모든 속성은 모델의 예측입니다. 같은 경계에 실선·점선 예측이 섞이거나, 구조물·연석·차량에 차선 표시가 생길 수 있습니다. 마스크가 점선 사이 빈 공간을 덮을 수도 있습니다.

[검증 절차]
1. 원본에서 차로 변경하는 대상 차량을 특정하세요.
2. 교차 전·중·후에 같은 차량을 보고 있는지 확인하세요.
3. 차량이 넘는 동일한 차선 경계를 특정하세요.
4. 원본에서 그 경계의 실제 페인트 색, 실선/점선, 단일선/이중선 여부를 확인하세요.
5. 차량이 그 경계의 한쪽에서 반대쪽으로 실제 이동했는지 시간 순서로 확인하세요.
차량과 선이 한 프레임에서 겹치거나 가까워 보인다는 사실만으로 교차를 확정하지 마세요. 카메라 이동, 차량 가림, 경계 변경, 잘못된 차선 표시를 고려하세요.

[증거 우선순위]
- 원본에서 관찰한 사실을 우선하세요.
- 차선 표시는 위치를 찾는 보조 정보로 사용하세요.
- 모델 예측과 원본이 다르면 원본을 따르고 불일치를 기록하세요.
- 페인트 색만으로 중앙선이나 차로 경계의 역할을 확정하지 마세요.
- 보이지 않는 구간이나 교차 순간을 추측해서 채우지 마세요.

[결과 기준]
- OBSERVED: 같은 차량이 원본에서 확인되는 실선 경계를 넘어 차로를 변경하는 과정이 확인됩니다.
- NOT_OBSERVED: 관찰 가능한 과정이 사건 조건과 맞지 않습니다. 예: 실제 경계가 점선이거나, 차량이 경계를 넘지 않았습니다.
- UNCERTAIN: 가림, 해상도, 관측 간격, 대상 차량이나 경계의 불명확성 때문에 필요한 증거를 확인할 수 없습니다. 증거 부족을 NOT_OBSERVED로 처리하지 마세요.
OBSERVED는 영상에서 해당 행위가 확인됐다는 뜻입니다. 법적 위반의 최종 확정을 의미하지 않습니다.

[반환 형식]
지정된 JSON 스키마만 반환하세요. 확인할 수 없는 시각·차량·위치는 null로 두세요.
event_type, verdict, target_vehicle, boundary(location, paint_color, pattern, line_count), crossing(before_sec, crossing_sec, after_sec), evidence(time_sec, observation), overlay_disagreements, missing_evidence, reason을 포함하세요.
evidence에는 원본에서 직접 관찰한 사실을 적으세요. 영상 B가 없으면 overlay_disagreements는 빈 배열로 두세요.
```

반환 스키마:

```json
{
  "$defs": {
    "Boundary": {
      "additionalProperties": false,
      "properties": {
        "location": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Location"
        },
        "paint_color": {
          "enum": [
            "WHITE",
            "YELLOW",
            "OTHER",
            "UNKNOWN"
          ],
          "title": "Paint Color",
          "type": "string"
        },
        "pattern": {
          "enum": [
            "SOLID",
            "DASHED",
            "MIXED",
            "UNKNOWN"
          ],
          "title": "Pattern",
          "type": "string"
        },
        "line_count": {
          "enum": [
            "SINGLE",
            "DOUBLE",
            "UNKNOWN"
          ],
          "title": "Line Count",
          "type": "string"
        }
      },
      "required": [
        "location",
        "paint_color",
        "pattern",
        "line_count"
      ],
      "title": "Boundary",
      "type": "object"
    },
    "Crossing": {
      "additionalProperties": false,
      "properties": {
        "before_sec": {
          "anyOf": [
            {
              "maximum": 40,
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "title": "Before Sec"
        },
        "crossing_sec": {
          "anyOf": [
            {
              "maximum": 40,
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "title": "Crossing Sec"
        },
        "after_sec": {
          "anyOf": [
            {
              "maximum": 40,
              "minimum": 0,
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "title": "After Sec"
        }
      },
      "required": [
        "before_sec",
        "crossing_sec",
        "after_sec"
      ],
      "title": "Crossing",
      "type": "object"
    },
    "Evidence": {
      "additionalProperties": false,
      "properties": {
        "time_sec": {
          "maximum": 40,
          "minimum": 0,
          "title": "Time Sec",
          "type": "number"
        },
        "observation": {
          "title": "Observation",
          "type": "string"
        }
      },
      "required": [
        "time_sec",
        "observation"
      ],
      "title": "Evidence",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "event_type": {
      "const": "SOLID_LINE_LANE_CHANGE",
      "title": "Event Type",
      "type": "string"
    },
    "verdict": {
      "enum": [
        "OBSERVED",
        "NOT_OBSERVED",
        "UNCERTAIN"
      ],
      "title": "Verdict",
      "type": "string"
    },
    "target_vehicle": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Target Vehicle"
    },
    "boundary": {
      "$ref": "#/$defs/Boundary"
    },
    "crossing": {
      "$ref": "#/$defs/Crossing"
    },
    "evidence": {
      "items": {
        "$ref": "#/$defs/Evidence"
      },
      "title": "Evidence",
      "type": "array"
    },
    "overlay_disagreements": {
      "items": {
        "type": "string"
      },
      "title": "Overlay Disagreements",
      "type": "array"
    },
    "missing_evidence": {
      "items": {
        "type": "string"
      },
      "title": "Missing Evidence",
      "type": "array"
    },
    "reason": {
      "title": "Reason",
      "type": "string"
    }
  },
  "required": [
    "event_type",
    "verdict",
    "target_vehicle",
    "boundary",
    "crossing",
    "evidence",
    "overlay_disagreements",
    "missing_evidence",
    "reason"
  ],
  "title": "Verification",
  "type": "object"
}
```
