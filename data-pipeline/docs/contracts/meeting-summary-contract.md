# Meeting Summary 계약

## 독립 작업

`SUMMARY`와 `NODES`는 STT와 정규화 결과만 공유하는 독립 task다. Java command의 `generateSummary`, `generateNodes`가 각각 task 생성을 결정한다. 둘 다 선택되면 Transcript를 한 번만 저장한 뒤 두 task를 병렬 실행한다. 각각 `WAITING_INPUT → READY → PROCESSING → SUCCEEDED|FAILED`로 전이하며 요청하지 않은 task는 `SKIPPED`다. 한 task의 실패는 다른 task 상태를 변경하지 않는다. 선택된 task는 최대 3회 시도하며 최종 실패에만 실패 Event v3를 발행한다.

신규 command 경로는 `analysis_delivery_state` 및 Graph+Summary 통합 성공 barrier를 사용하지 않는다. 해당 구조는 legacy 호환을 위해 DB에 남아 있을 뿐 신규 Result Event 생성에 관여하지 않는다.

## 저장과 멱등성

`meeting_summary`가 정본이다. `(project_id, external_meeting_id, summary_version)`은 유일하고, 동일 source hash의 재호출은 기존 결과를 반환한다. 다른 입력이 같은 version을 요구하면 충돌이다. summary 저장과 outbox 저장은 같은 transaction이다.

## 성공 이벤트

```json
{
  "eventSchemaVersion": 3,
  "eventId": "event-uuid",
  "eventType": "MEETING_SUMMARY_READY",
  "occurredAt": "2026-08-04T01:00:00Z",
  "projectId": 5,
  "meetingId": 35,
  "commandId": "command-uuid",
  "payload": {
    "meetingSummaryId": "summary-uuid",
    "summaryVersion": 1,
    "status": "READY",
    "apiPath": "/api/v1/meetings/35/summary?summaryVersion=1"
  }
}
```

본문은 SQS에 넣지 않는다. Java는 `apiPath`로 조회하고 `eventId`로 중복 제거한다.

제품 경로는 `GmsMeetingSummaryGenerator`가 기존 OpenAI 호환 GMS Client를 사용한다. 응답은 `title`, `body`, `decisions`, `actions`, `issues`의 엄격한 JSON 계약으로 검증한다. Fake 구현은 `tests/config/fake/`를 사용하는 local/test에만 허용하며 production coordinator는 시작 단계에서 모든 Fake AI adapter를 거부한다.
