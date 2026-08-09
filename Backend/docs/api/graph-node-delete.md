# Graph node delete API contract

Status: Java implementation complete / Python authoritative delete pending

The request endpoint participates in the project graph operation guard.
If another graph-changing command is active for the project, it returns
`409 Conflict` with error code `GRAPH_OPERATION_IN_PROGRESS`. The guard,
Pending Delete command, items, and command Outbox must be persisted atomically.
The rejection and success handlers release the guard only after
their state/projection transaction succeeds.

Java의 삭제 요청, Pending 조회 숨김, Result 처리 및 상태 조회가 구현되어 있다.
Python authoritative delete와 E2E 연동은 별도 작업이다.

## 삭제 요청

`POST /api/projects/{projectId}/nodes/delete`

`Content-Type: application/json`

### Request

```json
{
  "nodeIds": [
    "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "9c41bd63-0bed-4632-8334-7fdf42a48995"
  ],
  "expectedGraphVersion": 12
}
```

- `nodeIds`는 필수이며 1개 이상 1,000개 이하여야 한다.
- 각 `nodeId`는 null 또는 blank일 수 없고 소문자 canonical UUID 형식이어야 한다.
- 중복 ID는 Bean Validation 대상이 아니며 후속 Service 도메인 검증에서 처리한다.
- `expectedGraphVersion`은 0 이상이어야 한다. 현재 Graph Projection의 초기 version은 0이다.
- `expectedGraphVersion`은 signed 64-bit integer이다.
- 프론트는 선택 노드와 화면상 활성 자손 ID만 전송한다.
- 병합 원본 Node ID는 서버가 내부적으로 확장하며 요청에 포함하지 않는다.

### Accepted Response

`202 Accepted`의 data 영역은 다음 계약을 사용한다.

```json
{
  "commandId": "6aacd404-f36e-48fb-a821-f9f657bd829f",
  "projectId": 1,
  "nodeIds": [
    "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "9c41bd63-0bed-4632-8334-7fdf42a48995"
  ],
  "expectedGraphVersion": 12,
  "status": "PENDING"
}
```

응답의 `nodeIds`는 요청에서 접수된 활성 노드만 의미하며 서버가 확장한
`MERGED_SOURCE` ID는 노출하지 않는다.

## 삭제 상태 조회

`GET /api/projects/{projectId}/nodes/delete-commands/{commandId}`

### Response

```json
{
  "commandId": "6aacd404-f36e-48fb-a821-f9f657bd829f",
  "projectId": 1,
  "nodeIds": [
    "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "9c41bd63-0bed-4632-8334-7fdf42a48995"
  ],
  "expectedGraphVersion": 12,
  "resultGraphVersion": 13,
  "status": "SUCCEEDED",
  "reason": null,
  "requestedAt": "2026-08-07T10:30:00",
  "completedAt": "2026-08-07T10:30:02"
}
```

상태 조회의 `nodeIds`에도 `REQUESTED` Item만 포함하며 `MERGED_SOURCE` Item은
프론트에 노출하지 않는다.

- `resultGraphVersion`은 결과 전에는 null이며, 값이 있으면 signed 64-bit integer이다.
- Pending Item의 `expectedNodeVersion`도 signed 64-bit integer로 저장한다.

## 상태

| status | 의미 |
|---|---|
| `PENDING` | Java가 요청을 접수했고 최종 결과를 기다리는 상태 |
| `SUCCEEDED` | Python 삭제와 Java Projection 반영이 완료된 상태 |
| `REJECTED` | Python이 비즈니스 조건으로 삭제를 거부한 상태 |
| `FAILED` | Java가 Command를 SQS에 최종 발행하지 못한 상태 |

`PUBLISHED`, `PROCESSING`, `TIMEOUT` 상태는 사용하지 않는다. 발행 상태는 기존
Outbox가 관리한다.

### 상태 조회 응답 정책

- `nodeIds`에는 `REQUESTED` Item만 포함하며 내부 `MERGED_SOURCE` Item은 노출하지 않는다.
- `PENDING`: `reason`, `resultGraphVersion`, `completedAt`은 `null`이다.
- `SUCCEEDED`: Command에 저장된 `resultGraphVersion`을 반환하며 `reason`은 `null`이다.
- `REJECTED` / `FAILED`: 저장된 `reason`을 반환하며 `resultGraphVersion`은 `null`이다.
- Command가 없거나 다른 프로젝트에 속하면 `404 NODE_DELETE_COMMAND_NOT_FOUND`를 반환한다.
- 접근 권한은 기존 프로젝트 MEMBER 정책을 따른다.

## SQS 계약

Command Type은 `NODE_DELETE_REQUESTED`이며 기존 command schema version 1과
Envelope 필드를 그대로 사용한다.

```json
{
  "commandSchemaVersion": 1,
  "commandId": "6aacd404-f36e-48fb-a821-f9f657bd829f",
  "commandType": "NODE_DELETE_REQUESTED",
  "requestedAt": "2026-08-07T01:30:00Z",
  "projectId": 1,
  "payload": {
    "nodeIds": [
      "0afdda91-2576-54d3-bb87-8e9263b1d17c",
      "9c41bd63-0bed-4632-8334-7fdf42a48995"
    ],
    "expectedGraphVersion": 12,
    "requestedByMemberId": 15
  }
}
```

Command Payload에도 병합 원본 ID는 포함하지 않는다. Python이 원본 DB를
기준으로 병합 closure를 다시 계산한다.

성공은 기존 `PROJECT_GRAPH_CHANGED` 이벤트를 재사용한다.

- `sourceType`: `NODE_DELETE`
- `meetingId`: `null`
- 기존 `ProjectGraphChangedPayload` 구조와 event schema version 3은 변경하지 않는다.

비즈니스 거부는 `NODE_DELETE_REJECTED` 이벤트를 사용한다.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "792cbf87-b2ed-4010-a893-beb286597a47",
  "eventType": "NODE_DELETE_REJECTED",
  "occurredAt": "2026-08-07T01:30:02Z",
  "projectId": 1,
  "meetingId": null,
  "commandId": "6aacd404-f36e-48fb-a821-f9f657bd829f",
  "payload": {
    "sourceType": "NODE_DELETE",
    "reasonCode": "GRAPH_VERSION_CONFLICT"
  }
}
```

거부 reason은 `GRAPH_VERSION_CONFLICT`, `NODE_NOT_FOUND`,
`NODE_PROJECT_MISMATCH`, `NODE_DELETE_SET_INCOMPLETE`이다.
`COMMAND_PUBLISH_FAILED`는 Python 거부 코드가 아니라 Java의 내부 발행 실패
reason이며 상태는 `FAILED`이다.

## 현재 처리 지원 범위

- `NODE_DELETE_REJECTED`는 Parser, Envelope Validator, Reference Validator까지 지원한다.
- `NODE_DELETE_REJECTED` Handler는 아직 등록하지 않았으며 dispatch 시 handler unavailable로 실패한다.
- `PROJECT_GRAPH_CHANGED`의 `NODE_DELETE` source는 Reference Validation까지만 가능하다.
- 삭제 성공 Projection Applier가 없으므로 Payload Validator/Graph Handler에서 계속 명시적으로 거부한다.
- 거부 Handler 구현 시 Handler 등록과 readiness 필수 Event 목록 추가를 함께 수행해야 한다.
