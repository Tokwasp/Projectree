# Node content update API and SQS contract

## 처리 원칙

Java의 `ProjectNodeProjection`은 authoritative graph가 아니다. Java는 요청을 검증하고 기존
`meeting_analysis_command_outbox`에 command를 한 건 저장한다. Python이 authoritative graph를
수정하고 전체 snapshot을 만든 뒤 결과를 보내면 Java가 snapshot을 검증하고 projection 전체를
교체한다.

프로젝트별 graph mutation은 `ProjectGraphOperationGuard`로 한 번에 하나만 허용한다. Batch 요청
한 번은 commandId, guard 획득, outbox, SQS message, snapshot, graphVersion 증가가 각각 한 번이다.

## Version 의미

- `graphVersion`: 프로젝트 전체 graph snapshot 버전이다. Batch가 성공하면 변경 노드 수와 관계없이
  한 번 증가한다.
- `nodeVersion`: 개별 노드의 title/content가 실제 변경될 때 그 노드에서만 증가한다.
- `expectedNodeVersion`: 클라이언트가 마지막 조회에서 본 해당 노드의 `nodeVersion`이다. 별도 저장
  버전이 아니며 optimistic concurrency 검증 값이다.

Java projection 필드 `sourceNodeVersion`은 외부 계약의 현재 `nodeVersion`을 담는다.

## REST API

### V1 단건 API

`PATCH /api/projects/{projectId}/nodes/{nodeId}`

기존 API와 title/content 계약을 유지한다.

```json
{
  "title": "수정 제목",
  "content": "수정 내용",
  "expectedNodeVersion": 3
}
```

성공 시 `202 Accepted`와 기존 `NodeContentUpdateAcceptedResponse`를 반환한다.

### Batch API

`PATCH /api/projects/{projectId}/nodes`

```json
{
  "nodes": [
    {
      "id": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
      "title": "수정 제목 A",
      "expectedNodeVersion": 3
    },
    {
      "id": "45cd90e2-b0ae-4ba8-a361-20b70870d3c9",
      "title": "수정 제목 B",
      "expectedNodeVersion": 7
    }
  ]
}
```

`nodes`는 1~100개다. 각 item은 null일 수 없으며 소문자 canonical UUID `id`, 공백이 아닌
255자 이하 `title`, 양수 `expectedNodeVersion`이 필수다. 한 요청 안의 중복 id는 Java에서
`400 Bad Request`로 거절한다. 기존 project membership 정책을 동일하게 적용한다.

변경 노드가 있으면 `202 Accepted`:

```json
{
  "status": 202,
  "message": "성공",
  "data": {
    "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
    "requestedNodeCount": 3,
    "changedNodeCount": 2,
    "status": "PENDING"
  }
}
```

모두 no-op이면 `200 OK`:

```json
{
  "status": 200,
  "message": "성공",
  "data": {
    "commandId": null,
    "requestedNodeCount": 3,
    "changedNodeCount": 0,
    "status": "NO_CHANGE"
  }
}
```

## All-or-nothing과 no-op

Java는 프로젝트 잠금과 guard 획득 후 모든 대상의 소속, 존재/ACTIVE 상태,
`expectedNodeVersion == sourceNodeVersion`을 먼저 검증한다. 하나라도 실패하면 트랜잭션 전체가
롤백되어 guard와 outbox가 남지 않는다.

모든 버전 검증이 끝난 뒤 현재 projection title과 정규화된 요청 title이 같은 item을 실제 mutation
목록에서 제외한다. 일부 no-op이면 V2 `payload.nodes`에는 변경 item만 들어간다. 모두 no-op이면
outbox/SQS command를 만들지 않고 guard를 즉시 해제한다.

## SQS command V1: 단건

기존 단건 API는 다음 `commandSchemaVersion=1` 계약을 계속 발행한다.

```json
{
  "commandSchemaVersion": 1,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
  "requestedAt": "2026-08-06T06:30:00Z",
  "projectId": 4,
  "payload": {
    "nodeId": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "expectedNodeVersion": 3,
    "title": "수정 제목",
    "content": "수정 내용",
    "requestedByMemberId": 15
  }
}
```

V1 outbox는 `targetProjectId=projectId`, `targetNodeId=nodeId`, `meetingId=null`이다.

## SQS command V2: Batch

Batch API는 같은 commandType과 `commandSchemaVersion=2`를 사용한다. `nodes`에는 Java의 no-op
필터를 통과한 실제 변경 item만 들어간다.

```json
{
  "commandSchemaVersion": 2,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
  "requestedAt": "2026-08-06T06:30:00Z",
  "projectId": 4,
  "payload": {
    "nodes": [
      {
        "nodeId": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
        "expectedNodeVersion": 3,
        "title": "수정 제목 A"
      },
      {
        "nodeId": "45cd90e2-b0ae-4ba8-a361-20b70870d3c9",
        "expectedNodeVersion": 7,
        "title": "수정 제목 B"
      }
    ],
    "requestedByMemberId": 15
  }
}
```

V2 outbox는 `targetProjectId=projectId`, `targetNodeId=null`, `meetingId=null`이다. Python은 V2
`nodes` 전체를 하나의 transaction에서 all-or-nothing으로 검증하고 수정해야 한다. 노드별 command나
부분 성공을 만들면 안 된다.

## 성공 result와 snapshot 검증

V1/V2 모두 기존 result envelope schema 3과 `PROJECT_GRAPH_CHANGED`를 사용한다.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "792cbf87-b2ed-4010-a893-beb286597a47",
  "eventType": "PROJECT_GRAPH_CHANGED",
  "occurredAt": "2026-08-06T06:30:02Z",
  "projectId": 4,
  "meetingId": null,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "graphVersion": 12,
    "snapshotRef": {
      "bucket": "configured-graph-bucket",
      "objectKey": "graph-snapshots/project-4/version-12.json",
      "contentType": "application/json",
      "sizeBytes": 12345,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }
}
```

V1은 target node 존재, 요청한 title/content 일치, `nodeVersion` 증가를 기존 방식대로 검증한다.
V2는 저장된 command의 모든 item에 대해 다음을 검증한다.

1. snapshot에 `nodeId`가 존재한다.
2. snapshot title이 요청 title과 같다.
3. snapshot `nodeVersion == expectedNodeVersion + 1`이다.

Fresh V2 성공 result는 Java의 현재 `graphVersion + 1`과 정확히 일치해야 한다. 예를 들어 현재
버전이 10이면 result와 snapshot 버전은 모두 11이어야 하며 10이나 12는 contract violation이다.
이미 적용된 V2 result의 replay는 active command가 없고 `lastCommandId`가 result commandId와
같으며 result graphVersion이 현재 graphVersion과 같을 때만 허용한다.

모두 맞을 때만 전체 projection을 한 번 교체하고 `ProjectGraphSync.currentGraphVersion`을 한 번
갱신한 뒤 guard를 한 번 해제한다. 실제 변경된 노드만 `nodeVersion`이 1 증가해야 한다.

## NODE_CONTENT_UPDATE_REJECTED

Python의 business reject는 다음 envelope를 보낸다. Java가 지원하는 `reasonCode`와
`failedNodeId` 규칙은 다음과 같다.

- node-specific, `failedNodeId` 필수: `NODE_NOT_FOUND`, `NODE_NOT_EDITABLE`,
  `MERGED_SOURCE_NOT_EDITABLE`, `NODE_VERSION_CONFLICT`, `INVALID_CURRENT_REVISION`
- command-level, `failedNodeId` 생략 또는 null: `NO_CHANGE`, `GRAPH_SNAPSHOT_TOO_LARGE`

`failedNodeId`가 있으면 canonical UUID이며 해당 command에 실제 포함된 node id여야 한다.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "c50f01bc-516f-4d6b-b519-b739c93ac67c",
  "eventType": "NODE_CONTENT_UPDATE_REJECTED",
  "occurredAt": "2026-08-06T06:30:02Z",
  "projectId": 4,
  "meetingId": null,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "reasonCode": "NODE_VERSION_CONFLICT",
    "failedNodeId": "45cd90e2-b0ae-4ba8-a361-20b70870d3c9"
  }
}
```

Java는 inbox에 event를 멱등 등록하고 command/project/schema/failedNodeId reference를 검증한다.
projection과 graphVersion은 변경하지 않고, event commandId가 현재 guard owner일 때만 guard를
해제한다. 동일 eventId 재전달은 `DUPLICATE`로 처리한다.

Command-level rejection 예시:

```json
{
  "eventSchemaVersion": 3,
  "eventId": "0d105336-ab6d-497d-9b30-0249be73eb0d",
  "eventType": "NODE_CONTENT_UPDATE_REJECTED",
  "occurredAt": "2026-08-06T06:30:02Z",
  "projectId": 4,
  "meetingId": null,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "reasonCode": "GRAPH_SNAPSHOT_TOO_LARGE"
  }
}
```

## Backward compatibility

기존 단건 REST API, V1 SQS payload, title/content 지원은 유지한다. Batch 추가는 meeting analysis와
node delete command/result 흐름을 변경하지 않는다. Command publish 실패 처리도 V1/V2 모두 기존
`NODE_CONTENT_UPDATE_REQUESTED` 분기를 사용해 해당 프로젝트 guard를 해제한다.
