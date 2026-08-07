# Node Content Update Command v1

상태: 현재 제품 계약 (Result Event v3)

이미 PostgreSQL에 저장된 canonical Project Graph Node의 제목·본문을 사용자가
사후 수정하는 경로다. 회의 분석을 다시 실행하지 않으며 기존 Java Command Queue,
Python command consumer, Full Graph Snapshot Artifact, Result Outbox와 Publisher를
그대로 사용한다.

## 입력

```json
{
  "commandSchemaVersion": 1,
  "commandId": "UUID",
  "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
  "requestedAt": "2026-08-07T01:15:00Z",
  "projectId": 1,
  "payload": {
    "nodeId": "UUID",
    "expectedNodeVersion": 3,
    "title": "사용자가 승인한 제목 또는 null",
    "content": "사용자가 승인한 본문 또는 null",
    "requestedByMemberId": 15
  }
}
```

`title`과 `content` 중 하나 이상은 non-null이어야 한다. non-null title은 공백만
있을 수 없고 255자 이하이며, content는 공백만 있을 수 없고 65,535자 이하이다.
content의 앞뒤 공백은 보존한다. project/member/version은 양의 signed 64-bit
정수이고 UUID와 requestedAt은 canonical UUID 및 UTC `Z` 형식이다.

## 적용 규칙

- 같은 project의 삭제되지 않고 병합되지 않은 `ACTIVE|UNATTACHED` Node만 수정한다.
- Node를 row lock한 뒤 `expectedNodeVersion`을 검사한다.
- 실제 값이 같으면 NO_OP으로 완료하며 Node/Graph version, Revision, Snapshot을
  만들지 않는다.
- 변경 시 기존 Evidence와 Node metadata를 보존한 새 USER `NodeRevision`을 만들고
  `current_revision_id`, Node projection과 Node version을 함께 갱신한다.
- canonical embedding hash가 바뀐 경우 READY Embedding을 STALE로 만들고 Node
  analysis를 STALE, 현재 PENDING/RUNNING/COMPLETED Run을 SUPERSEDED로 만든다.
- 사용자 수정 뒤 자동 merge는 USER provenance인 title/content를 보존하고 Evidence만
  추가한다.

## 멱등성과 트랜잭션

`commandId + canonical payload SHA-256`을 기존 command inbox에 저장한다.

- 같은 commandId + 같은 payload: 완료/실패 결과를 재사용한다.
- 같은 commandId + 다른 payload: `COMMAND_ID_PAYLOAD_CONFLICT`이다.
- 서로 다른 commandId가 같은 expected version으로 경합하면 row lock 이후 하나만
  성공하고 나머지는 `NODE_VERSION_CONFLICT`로 기록된다.

Revision, Embedding/Analysis 상태, graphVersion, Full Snapshot Artifact,
`PROJECT_GRAPH_CHANGED` Outbox와 command 완료 상태는 한 DB transaction에서 commit한다.
S3 및 Result SQS 실패는 기존 Outbox Publisher가 같은 Artifact와 eventId로 재시도한다.

## Result Event와 Snapshot

성공 시 Result Event v3 `PROJECT_GRAPH_CHANGED`를 사용한다.

```json
{
  "eventSchemaVersion": 3,
  "eventType": "PROJECT_GRAPH_CHANGED",
  "projectId": 1,
  "meetingId": null,
  "commandId": "NODE_CONTENT_UPDATE_REQUESTED commandId",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "graphVersion": 12,
    "snapshotRef": {"bucket": "...", "objectKey": "..."}
  }
}
```

Snapshot도 top-level `meetingId=null`이며 기존 Full Graph Snapshot v1 serializer를
사용한다. 각 Node의 `sourceMeetingId`와 Evidence의 `meetingId`는 바꾸지 않는다.

Java에 Node mutation 전용 실패 Event 계약은 아직 없으므로 business failure는
Python command inbox에 `FAILED`와 failure code로 기록하고 성공 Snapshot/Event를
만들지 않는다. 잘못된 JSON/schema는 기존 SQS redrive/DLQ 정책을 따른다.
