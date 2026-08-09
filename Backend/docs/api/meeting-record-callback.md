# 회의록 Callback 계약 (Python → Java)

Python 분석 서버가 회의 요약 생성에 성공한 뒤, 회의록 초안을 Java에 전달하는 내부 API다.

회의록 데이터의 최종 소유권은 Java가 가진다. 이 Callback은 **회의록 최초 생성만** 담당하며,
같은 회의록을 수정하거나 덮어쓰지 않는다. 사용자의 회의록 수정은 별도의 프론트엔드 API로 처리된다.

## Endpoint

```
PUT /api/internal/meetings/{meetingId}/record
```

- `meetingId` — Java가 Command SQS로 보낸 payload의 `payload.meetingId`를 그대로 사용한다.

## Headers

```
Content-Type: application/json
X-Internal-Api-Key: {shared secret}
```

- 공유 비밀은 Java의 `MEETING_RECORD_CALLBACK_API_KEY` 환경변수와 동일한 값이어야 한다.
- 헤더가 없거나 값이 다르면 `401`이다.

## Request Body

```json
{
  "callbackSchemaVersion": 1,
  "commandId": "0fcaeb2d-8f50-4ced-a081-54faf4de9f37",
  "title": "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의",
  "summary": [
    "첫 번째 전체 요약",
    "두 번째 전체 요약"
  ],
  "decisions": [
    "첫 번째 결정 사항"
  ],
  "nextTodos": [
    "첫 번째 다음 할 일"
  ],
  "issues": [
    "첫 번째 이슈"
  ]
}
```

### 필드 규칙

| 필드 | 타입 | 규칙 |
|---|---|---|
| `callbackSchemaVersion` | int | 필수, 현재 `1`만 허용 |
| `commandId` | UUID 문자열 | 필수. Java Command SQS payload의 `commandId`를 그대로 사용한다 |
| `title` | string | 필수, blank 금지, 최대 200자 |
| `summary` | string 배열 | 필수. null 금지, 비어 있으면 `[]`. 크기 제한 있음 (아래 참고) |
| `decisions` | string 배열 | 필수. null 금지, 비어 있으면 `[]`. 크기 제한 있음 |
| `nextTodos` | string 배열 | 필수. null 금지, 비어 있으면 `[]`. 크기 제한 있음 |
| `issues` | string 배열 | 필수. null 금지, 비어 있으면 `[]`. 크기 제한 있음 |

- 네 배열 모두 **null을 보내면 안 된다.** 값이 없으면 빈 배열 `[]`을 보낸다.
- 배열 내부에 `null`이나 공백만 있는 문자열을 넣으면 `400`이다.
- **배열 항목의 순서는 그대로 보존되어 저장되고, 조회 시 같은 순서로 반환된다.**
- `projectId`와 `roomName`은 보내지 않는다. `commandId`와 `meetingId`로 검증이 충분하다.

### 배열 영역별 크기 제한

네 배열은 각각 **독립적으로** 크기 제한을 가진다. 합산이 아니라 영역별로 검사한다.

- 한 영역의 직렬화 결과가 **65,535바이트(UTF-8)** 를 넘으면 `400 MEETING_RECORD_CONTENT_TOO_LARGE`다.
- 기준은 문자 개수가 아니라 **UTF-8 바이트 수**다. 한국어는 한 글자가 보통 3바이트이므로
  한 영역에 한국어 약 21,000자를 넣으면 한도에 가까워진다.
- 따옴표·역슬래시·줄바꿈은 JSON escape로 바이트가 늘어나므로, 여유를 두고 보내는 것이 안전하다.
- 한 영역이라도 초과하면 **회의록 전체가 저장되지 않는다.** 부분 저장은 없다.

## Response

성공 시 `200 OK`이며 공통 응답 형식으로 감싸진다.

```json
{
  "status": 200,
  "message": "성공",
  "data": {
    "meetingRecordId": 91,
    "meetingId": 35,
    "commandId": "0fcaeb2d-8f50-4ced-a081-54faf4de9f37",
    "version": 0,
    "duplicated": false
  }
}
```

- `duplicated: false` — 이번 요청으로 회의록을 새로 생성했다.
- `duplicated: true` — 이미 회의록이 있어 기존 회의록을 그대로 반환했다. **아무것도 변경되지 않았다.**
- `version` — 회의록의 낙관적 락 버전. 사용자가 수정하면 증가한다.

최초 생성과 재시도 모두 `200`이므로, Python은 성공을 단일 상태 코드로 판정할 수 있다.
`201`은 사용하지 않는다.

## 오류와 재시도 정책

| Status | errorCode | 의미 | 재시도 |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | 필수 필드 누락, 형식 오류, 배열 내 null/blank | **금지** |
| 400 | `MEETING_RECORD_CALLBACK_SCHEMA_UNSUPPORTED` | `callbackSchemaVersion`이 1이 아님 | **금지** |
| 400 | `MEETING_RECORD_CONTENT_TOO_LARGE` | 특정 회의록 영역이 허용 크기를 초과함 | **금지** (아래 참고) |
| 401 | `MEETING_RECORD_CALLBACK_UNAUTHORIZED` | API Key 누락 또는 불일치 | **금지** |
| 404 | `MEETING_RECORD_COMMAND_NOT_FOUND` | `commandId`에 해당하는 분석 요청이 없음 | **금지** |
| 404 | `MEETING_NOT_FOUND` | `meetingId`에 해당하는 회의가 없음 | **금지** |
| 409 | `MEETING_RECORD_COMMAND_MISMATCH` | `commandId`가 다른 회의의 분석 요청임 | **금지** |
| 409 | `MEETING_RECORD_SUMMARY_NOT_REQUESTED` | 요약 생성을 요청하지 않은 회의 | **금지** |
| 409 | `MEETING_RECORD_SUMMARY_ALREADY_FAILED` | 해당 분석 요청이 이미 실패로 확정됨 | **금지** |
| 409 | `MEETING_RECORD_ALREADY_CREATED_BY_ANOTHER_COMMAND` | 다른 분석 요청으로 만들어진 회의록이 이미 존재 | **금지** |
| 5xx / 네트워크 timeout | — | 예상하지 못한 DB 오류, 일시적 서버 오류, 네트워크 오류 | **재시도** |

- `4xx`는 요청 자체가 잘못된 것이므로 재시도하면 같은 결과가 반복된다.
- **재시도는 `5xx`와 네트워크 timeout에만 적용한다.** 여기에는 예상하지 못한 DB 오류,
  일시적인 서버 오류, 연결 실패가 포함된다. Java는 이런 오류를 비즈니스 충돌(`4xx`)로
  숨기지 않고 `5xx`로 그대로 노출하므로, 재시도하면 성공할 수 있다.
- **재시도할 때는 최초 요청과 같은 `meetingId`, 같은 `commandId`를 사용한다.**

### `400 MEETING_RECORD_CONTENT_TOO_LARGE` 대응

동일 Payload를 그대로 다시 보내면 반드시 같은 오류가 반복된다. **동일 Payload 자동 재시도를 하지 않는다.**

이 오류가 발생한 시점에는 회의록이 저장되지 않았고 회의의 요약 상태도 그대로 `PROCESSING`이다.
따라서 **같은 `commandId`로 크기를 줄인 Payload를 다시 보내면 정상 저장된다.**
동일 회의의 재분석 요청은 지원하지 않으므로, 새 `commandId`를 발급받는 방식은 사용할 수 없다.

Python 쪽 권장 처리:

- 하나의 영역에 지나치게 많은 텍스트를 몰아넣지 않는다.
- 응답 생성 후 각 배열 영역의 JSON 직렬화 크기를 미리 확인한다.
- 이 오류가 발생하면 요약 길이를 줄이거나 항목 수를 줄여 **같은 `commandId`로 다시 호출한다.**

### `409 MEETING_RECORD_SUMMARY_ALREADY_FAILED` 대응

해당 분석 요청은 이미 실패로 확정되어 회의 상태가 `FAILED`다.
실패 이벤트가 성공 Callback보다 먼저 도착한 경우에 발생한다.

- 성공 Callback을 다시 보내도 **저장되지 않는다.** 자동 재시도를 하지 않는다.
- **현재 백엔드는 동일 회의의 재분석 요청을 지원하지 않는다.** 한 회의의 분석 요청은
  한 번만 확정할 수 있고, 분석 요청 Command도 회의당 하나만 존재할 수 있다.
  따라서 새 `commandId`를 발급받을 방법이 없다.
- 재분석 기능이 별도로 추가되기 전까지는 **해당 회의를 실패 상태로 종료한다.**
- Java가 이 요청을 거부하는 이유는, 회의록은 저장됐지만 분석 상태는 실패인
  모순 상태를 만들지 않기 위함이다.

### 재시도 권고 (Python 쪽에서 구현)

```
1초 → 2초 → 4초, 최대 3회
```

Java는 재시도 로직을 구현하지 않는다. 위 정책은 호출자 권고 사항이다.

## 멱등성 보장

- 같은 `commandId`로 몇 번을 재시도해도 회의록은 **정확히 1건만** 생성된다.
- 동일 `commandId` 재시도 시 Java는 **요청 본문을 무시하고 기존 회의록을 그대로 반환한다.**
  요청의 `title`이나 본문이 기존 데이터와 달라도 덮어쓰지 않으며, `version`도 증가하지 않는다.
- 이는 사용자가 회의록을 수정한 뒤 Python이 Callback을 재시도했을 때
  **사용자 편집 내용이 사라지지 않도록** 하기 위한 정책이다.
- 같은 회의에 대한 동시 Callback은 회의 단위 비관적 락으로 직렬화되므로,
  두 요청이 동시에 도착해도 하나는 생성, 다른 하나는 `duplicated: true`로 처리된다.

## 부수 효과

Callback이 최초로 성공하면 해당 회의의 요약 분석 상태(`summaryStatus`)가 `SUCCEEDED`로 전이된다.
재시도는 이미 완료된 상태를 다시 변경하지 않는다.

상태별 처리:

| Callback 도착 시점의 요약 상태 | 처리 |
|---|---|
| `PROCESSING` | 회의록 저장, 상태를 `SUCCEEDED`로 전이 |
| `SUCCEEDED` (회의록 없음) | 회의록 저장. SQS 이벤트가 먼저 도착해 상태만 바뀐 경우 |
| `SUCCEEDED` (회의록 있음) | `duplicated: true`로 기존 회의록 반환 |
| `FAILED` | `409 MEETING_RECORD_SUMMARY_ALREADY_FAILED`, 저장하지 않음 |

회의록 저장과 상태 전이는 하나의 트랜잭션이다. 어느 쪽이 실패하면 둘 다 반영되지 않는다.
