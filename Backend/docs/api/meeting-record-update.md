# 회의록 전체 수정 API

## Endpoint

`PUT /api/projects/{projectId}/meetings/{meetingId}/record`

로그인이 필요하며, 해당 프로젝트의 멤버 중 회의를 생성한 사용자만 수정할 수 있다.
부분 수정이 아닌 전체 문서 교체 API이므로 네 본문 배열을 모두 보내야 한다.

## Request

```json
{
  "title": "수정한 회의 제목",
  "summary": ["수정한 전체 요약입니다."],
  "decisions": ["수정한 결정 사항입니다."],
  "nextTodos": ["수정한 다음 할 일입니다."],
  "issues": ["수정한 이슈입니다."],
  "version": 0
}
```

- `title`: 필수, 공백 불가, 최대 200자
- 네 본문 배열: 필수. 빈 배열은 허용하지만 `null` 또는 공백 항목은 허용하지 않는다.
- `version`: 필수인 0 이상의 정수. 직전 GET 응답의 `version`을 그대로 보낸다.
- 각 본문 배열은 JSON으로 저장되며, 영역별 UTF-8 인코딩 결과가 MySQL `TEXT`
  한도인 65,535바이트를 넘을 수 없다.

## Response

정상 응답은 `200 OK`이며 저장 후 증가한 `version`과 `updatedAt`을 반환한다.

```json
{
  "status": 200,
  "message": "성공",
  "data": {
    "meetingRecordId": 12,
    "projectId": 3,
    "meetingId": 35,
    "title": "수정한 회의 제목",
    "summary": ["수정한 전체 요약입니다."],
    "decisions": ["수정한 결정 사항입니다."],
    "nextTodos": ["수정한 다음 할 일입니다."],
    "issues": ["수정한 이슈입니다."],
    "version": 1,
    "updatedAt": "2026-08-05T17:00:00"
  }
}
```

수정 응답에는 `commandId`, 참여자, 추정 회의 시간 필드가 포함되지 않는다.

## 동시 수정

서버는 요청의 `version`을 먼저 비교하고 JPA `@Version`으로 실제 동시 쓰기를
방어한다. 다른 수정이 먼저 반영되었으면 다음 오류를 반환하며 요청 본문을 저장하지 않는다.

`409 MEETING_RECORD_VERSION_CONFLICT`

프론트는 로컬 초안을 자동 폐기하거나 강제로 덮어쓰지 않는다. GET으로 최신 회의록을 다시
조회하고 충돌 사실을 알린 뒤, 사용자가 최신 내용을 기준으로 다시 편집하도록 한다.

## 오류

| HTTP | errorCode | 의미 |
|---:|---|---|
| 400 | `INVALID_REQUEST` | Request validation 실패 |
| 400 | `MEETING_PROJECT_MISMATCH` | URL 프로젝트와 회의의 프로젝트 불일치 |
| 400 | `MEETING_RECORD_CONTENT_TOO_LARGE` | 본문 영역의 TEXT 크기 초과 |
| 401 | `UNAUTHORIZED` | 로그인 필요 |
| 403 | `MEETING_RECORD_UPDATE_FORBIDDEN` | 회의 생성자가 아님 |
| 404 | `PROJECT_NOT_FOUND` | 프로젝트 없음 |
| 404 | `PROJECT_PARTICIPANT_NOT_FOUND` | 프로젝트 멤버가 아님 |
| 404 | `MEETING_NOT_FOUND` | 회의 없음 |
| 404 | `MEETING_RECORD_NOT_FOUND` | 회의록 없음 |
| 409 | `MEETING_RECORD_VERSION_CONFLICT` | stale version 또는 동시 수정 충돌 |
| 500 | `INTERNAL_SERVER_ERROR` | 처리 중 예상하지 못한 오류 |
