# Node Content Update Command v2

상태: 현재 제품 계약 (Result Event v3)

이미 PostgreSQL에 저장된 같은 프로젝트의 canonical Node 제목을 한 명령에서 1~100개
수정한다. V1 단건 제목·본문 수정과 동일한 `commandType`을 사용하되
`commandSchemaVersion=2`로 payload를 구분한다. LLM과 회의 분석은 호출하지 않는다.

## 입력

```json
{
  "commandSchemaVersion": 2,
  "commandId": "550e8400-e29b-41d4-a716-446655440000",
  "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
  "projectId": 15,
  "requestedAt": "2026-08-09T07:30:00Z",
  "payload": {
    "nodes": [
      {
        "nodeId": "123e4567-e89b-12d3-a456-426614174000",
        "expectedNodeVersion": 3,
        "title": "사용자가 승인한 최종 제목"
      }
    ],
    "requestedByMemberId": 15
  }
}
```

`nodes`는 1~100개이며 `nodeId`는 중복될 수 없다. 각 title은 문자열이고 trim 후
비어 있지 않으며 원문 길이 255자 이하다. V2는 content 수정을 지원하지 않는다.
project/member는 양의 signed 64-bit JSON 정수, expected version은 양의 signed 32-bit
JSON 정수다. UUID는 canonical text, requestedAt은 UTC `Z` 형식이어야 한다.

## 원자성과 버전

Python은 Project graph state를 한 번 잠근 다음 대상 Node를 UUID 순서로 잠근다. 모든
Node의 프로젝트·상태·병합 계보·expected version·현재 Revision/Evidence를 preflight한
후에만 첫 변경을 시작한다. 하나라도 실패하면 어떤 Node도 수정하지 않는다.

실제 제목이 바뀐 Node만 USER Revision과 GraphChangeEvent를 만들고 nodeVersion을 1
증가시킨다. 일부 no-op은 유지한다. 변경 Node가 하나 이상이면 명령 전체에서
graphVersion, Full Snapshot, `PROJECT_GRAPH_CHANGED`를 각각 한 번만 생성한다. 전체가
no-op이면 `NO_CHANGE`로 거절하며 어떤 graph artifact도 만들지 않는다.

Embedding input hash가 바뀐 변경 Node만 READY Embedding과 Analysis를 기존 V1 정책으로
무효화한다. no-op Node의 Revision, version, Embedding과 Analysis는 변경하지 않는다.

## 성공 Result

Outbox Publisher가 Snapshot을 S3에 업로드한 뒤 실제 wire event는 다음 형태다.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "UUID",
  "eventType": "PROJECT_GRAPH_CHANGED",
  "occurredAt": "2026-08-09T07:30:01.000000Z",
  "projectId": 15,
  "meetingId": null,
  "commandId": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "graphVersion": 12,
    "snapshotRef": {
      "bucket": "configured-result-bucket",
      "objectKey": "graph-snapshots/project-15/command-550e8400-e29b-41d4-a716-446655440000/v12.json",
      "contentType": "application/json",
      "sizeBytes": 1234,
      "sha256": "lowercase-hex"
    }
  }
}
```

## 실패 Result

결정적인 V2 실패는 command inbox의 `FAILED` 상태와 같은 트랜잭션에서 다음 event를
저장한 뒤 입력 SQS를 ACK한다.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "UUID",
  "eventType": "NODE_CONTENT_UPDATE_REJECTED",
  "occurredAt": "2026-08-09T07:30:01.000000Z",
  "projectId": 15,
  "meetingId": null,
  "commandId": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "reasonCode": "NODE_VERSION_CONFLICT",
    "failedNodeId": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

reasonCode는 다음 중 하나다.

- `NODE_NOT_FOUND`
- `NODE_NOT_EDITABLE`
- `MERGED_SOURCE_NOT_EDITABLE`
- `NODE_VERSION_CONFLICT`
- `INVALID_CURRENT_REVISION`
- `NO_CHANGE`
- `GRAPH_SNAPSHOT_TOO_LARGE`

`NO_CHANGE`와 `GRAPH_SNAPSHOT_TOO_LARGE`의 `failedNodeId`는 `null`이다. 예상하지 못한
DB/AWS/직렬화 오류는 terminal rejection으로 위장하지 않고 rollback 후 예외를 다시
발생시켜 SQS가 ACK되지 않게 한다.

## 멱등성

Batch 전체는 한 `meeting_analysis_command` row에 저장한다. V2 canonical payload hash는
schema version, command/envelope 값, 요청 순서 그대로의 nodes 전체와 member id를 포함한다.

- 같은 commandId + 같은 payload: 기존 Snapshot/Result를 replay하고 새 mutation을 만들지 않는다.
- 같은 commandId + 다른 payload 또는 V1/V2 혼용: `COMMAND_ID_PAYLOAD_CONFLICT`다.
