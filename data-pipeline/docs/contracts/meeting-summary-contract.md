# Meeting Summary 계약

## 작업과 상태

`SUMMARY`는 `NODES`와 정규화 Transcript만 공유하는 독립 task다. Java command의
`generateSummary`가 task 생성 여부를 결정하며 상태는
`WAITING_INPUT → READY → PROCESSING → SUCCEEDED|FAILED`로 전이한다.
요청되지 않은 task는 `SKIPPED`다. Summary 성공 여부는 아래 두 조건을 모두 만족해야 한다.

```text
Python PostgreSQL에 MeetingSummary 저장 완료
AND
Java meeting-record HTTP Callback 200 응답
```

Callback이 끝나기 전에는 Coordinator가 `SUMMARY` task를 `SUCCEEDED`로 만들지 않는다.

## 생성 결과

Provider는 다음 다섯 키만 가진 JSON 객체를 반환한다.

```json
{
  "title": "회의 제목",
  "summary": [],
  "decisions": [],
  "nextTodos": [],
  "issues": []
}
```

- `title`: trim 후 1~200자
- 네 배열: 항상 존재하고 null이 아니며, 순서를 보존한 non-blank 문자열만 포함
- 배열 요소에 `- `, `* `, `• ` 같은 bullet prefix를 넣지 않음
- 각 배열은 최대 500개이며 compact JSON UTF-8 직렬화 크기가 60,000 bytes 이하여야 함
- 근거 없는 사실·담당자·기한·결정·이슈를 생성하지 않음
- GMS prompt version은 `meeting-summary-v2`

Provider 응답의 `body`, `actions` 키는 허용하지 않는다.

## PostgreSQL 매핑과 멱등성

새 migration 없이 기존 `meeting_summary`를 사용한다.

```text
title              = generated.title.strip()
body               = "\n".join(generated.summary)
structured_summary = {
  "summary": [...],
  "decisions": [...],
  "nextTodos": [...],
  "issues": [...]
}
```

`summary=[]`이면 `body`는 빈 문자열이다. 동일
`(project_id, external_meeting_id, summary_version)`과 동일 source hash의 재호출은 저장된
결과를 반환하며 Provider를 다시 호출하지 않는다. source hash가 다르면 충돌이다.

과거 데이터로 Callback body를 만들 때만 다음 읽기 호환을 적용한다.

- `structured_summary.summary`가 없고 `body`가 non-blank이면 `summary=[body]`
- `actions`는 `nextTodos`로 변환
- 신규 저장은 오직 새 키를 사용

## Java HTTP Callback

Command 기반 Summary 성공 결과는 다음 요청으로만 전달한다.

```http
PUT {JAVA_BASE_URL}/api/internal/meetings/{meetingId}/record
Content-Type: application/json
X-Internal-Api-Key: {MEETING_RECORD_CALLBACK_API_KEY}
```

```json
{
  "callbackSchemaVersion": 1,
  "commandId": "원래 command UUID",
  "title": "회의 제목",
  "summary": [],
  "decisions": [],
  "nextTodos": [],
  "issues": []
}
```

`meetingId`는 URL path에만 사용한다. `projectId`, `roomName`, task flags, version과 시간은
body에 넣지 않는다. 200 응답의 `duplicated=false`와 `duplicated=true`는 모두 성공이다.

HTTP 5xx, timeout, connection/network error만 1초·2초·4초 간격으로 재시도하며 최대
HTTP 요청은 4회다. 모든 시도는 같은 meetingId, commandId, body를 사용한다. 일반 4xx는
재시도하지 않는다.

`MEETING_RECORD_CONTENT_TOO_LARGE`만 예외적으로 저장된 원본은 바꾸지 않고 Callback
배열을 결정적으로 축약해 한 번 추가 전송한다. title, meetingId, commandId와 배열 순서는
유지하고 가장 큰 배열부터 뒤쪽 항목을 제거한다. 단일 항목이 큰 경우 Unicode 문자
경계에서 뒤를 잘라 각 배열을 50,000 bytes 이하로 만든다. 축약 요청도 실패하면 즉시
최종 실패하며 GMS를 다시 호출하지 않는다.

`MEETING_RECORD_SUMMARY_ALREADY_FAILED`는 성공이 아니며 동일 실패 Result event도 다시
발행하지 않는다.

Callback 재실행은 PostgreSQL의 기존 `MeetingSummary`를 재사용하며 GMS를 재호출하지 않는다.

## 성공·실패 통지

Command 기반 성공에는 `MEETING_SUMMARY_READY`를 발행하지 않는다. 성공 통지는 위 HTTP
Callback뿐이다. Command가 없는 legacy Summary 경로와 기존 조회 API는 호환을 위해 예전
이벤트 계약을 유지한다.

최종 실패는 기존 Result Outbox의 `ANALYSIS_TASK_STATUS_CHANGED`를 사용한다.

```text
taskType = SUMMARY
status = FAILED
failureCode = SUMMARY_GENERATION_FAILED
            | SUMMARY_CALLBACK_REJECTED
            | SUMMARY_CALLBACK_DELIVERY_FAILED
failureCode = non-blank, 최대 100자
failureMessage = non-blank, 최대 1,000자
```

Coordinator만 최종 실패 이벤트를 만들며 processor는 별도 Outbox를 생성하지 않는다.

## 환경변수와 보안

```dotenv
SUMMARY_ADAPTER=gms
JAVA_BASE_URL=https://api.example.com
MEETING_RECORD_CALLBACK_API_KEY=replace-with-shared-secret
MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS=10
```

API key, 전체 Callback body, 전체 Transcript 및 전체 사용자 발화는 로그에 남기지 않는다.
Callback client는 runtime당 한 번 생성해 재사용하고 종료 시 close한다.
