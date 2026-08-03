# Meeting Summary 계약

## 경계

회의 Node 생성·병합과 회의록 본문 생성은 별도 기능이다.
`GenerationRun.result_summary`는 그래프 적용 통계이며 회의록 본문이 아니다.
`MINUTES_ONLY`도 회의록 생성 상태가 아니다.

현재 실제 외부 LLM 구현은 연결하지 않는다. `MeetingSummaryGenerator` port와
`FakeMeetingSummaryGenerator`만 제공하며 실제 품질은 credit 정책에 따라
`NOT_EVALUATED_CREDIT_BLOCKED`다.

## 정본과 버전

`meeting_summary`가 회의록 정본이다. 한 프로젝트·외부 회의 ID 안에서
`summary_version`은 양수이며 유일하다. 저장된 버전은 수정하지 않고 새 버전을
추가한다. 같은 transcript source hash로 같은 버전을 재호출하면 기존 결과를
멱등 반환한다. 같은 버전에 다른 입력이 들어오면 충돌로 거부한다.

저장 필드:

- 실제 본문: `title`, `body`
- 구조화 항목: `decisions`, `actions`, `issues`를 담은 `structured_summary`
- 계보: `source_hash`, `generator_name`, `generator_version`
- 공개 상태: `READY`

## 원자성 및 전달

회의록 INSERT와 `MEETING_SUMMARY_READY` Outbox INSERT는 같은 트랜잭션이다.
Spring/Java는 이벤트 본문에 전체 회의록을 받지 않고 아래 식별자와 조회 경로를
받는다.

```json
{
  "meetingSummaryId": "UUID",
  "projectId": "project-id",
  "externalMeetingId": "meeting-id",
  "summaryVersion": 1,
  "status": "READY",
  "apiPath": "/api/v1/meetings/meeting-id/summary?summaryVersion=1"
}
```

조회 API:

```text
GET /api/v1/meetings/{externalMeetingId}/summary
GET /api/v1/meetings/{externalMeetingId}/summary?summaryVersion=1
X-Project-Id: <project scope>
```

버전을 생략하면 가장 최신 버전을 반환한다. 다른 프로젝트의 회의록은 404로
숨긴다. Outbox는 at-least-once이므로 Spring은 envelope의 `eventId`로 중복을
제거해야 한다.
