# Node Delete Command v1

Java의 Node 논리 삭제 요청은 기존 Command SQS·기존 Command Inbox·기존 Outbox
Publisher·기존 Result SQS·기존 Snapshot Bucket을 그대로 쓴다. 전용 Queue, 전용
Snapshot Generator, 전용 Command 테이블을 만들지 않는다.

## Command

```json
{
  "commandSchemaVersion": 1,
  "commandId": "3f1c1a1e-6d9a-4a8e-9d5a-2f0f7a8e1b23",
  "commandType": "NODE_DELETE_REQUESTED",
  "requestedAt": "2026-08-07T01:15:00Z",
  "projectId": 1,
  "payload": {
    "nodeIds": ["9b8f0a2c-4c8e-4b0e-9a1f-1d2c3b4a5e6f"],
    "expectedGraphVersion": 12,
    "requestedByMemberId": 15
  }
}
```

`nodeIds`는 비어 있지 않은 canonical UUID 문자열 배열(최대 10,000개)이다.
`expectedGraphVersion`은 0 이상 정수다. 0을 거부하지 않는 이유는 stale한 값을
파싱 불가 message로 queue에 남기지 않고 durable한 `GRAPH_VERSION_CONFLICT`
rejection으로 끝내기 위해서다.

`nodeIds`는 **삭제 seed**다. Java나 Frontend가 descendants를 이미 포함해 보내도
되고 중복이 있어도 된다. 실제 삭제 집합은 Python authoritative PostgreSQL이
계산한다.

## Effective delete set

```text
effectiveDeleteIds = seed ids + 모든 structural descendants + 모든 reverse merged sources
```

두 확장은 하나의 fixpoint loop에서 동시에 수행한다.

- **Descendant closure** — seed의 자식(`parent_id`)을 재귀적으로 포함한다. 부분
  삭제 후 child를 `UNATTACHED`로 남기지 않는다. 이 경로에서 부모 삭제로 살아남는
  child는 없다.
- **Reverse merge closure** — 삭제 대상 `T`에 대해 `merged_into_node_id = T`인
  `MERGED` source를 포함하며 transitive하다. 방향은 한쪽뿐이다. `MERGED` source를
  seed로 지정해도 그 canonical target은 삭제되지 않는다.

삭제 가능 상태는 `ACTIVE`, `MERGED`, `UNATTACHED`다. 이미 `deleted_at`이 있거나
`EXCLUDED`/`ARCHIVED`인 Node는 살아 있는 graph Node가 아니므로 seed로 지정되면
`NODE_NOT_FOUND`로 reject한다.

Commit 직전과 mutation 직후 두 번, 살아남은 Node가 삭제된 Node를 `parent_id`나
`merged_into_node_id`로 참조하지 않는지 검증한다.

## Version

`nodeVersion`과 `graphVersion`은 분리 유지한다.

- 논리 삭제되는 **각** Node는 기존 revision 경로를 거치며 `nodeVersion +1`이다.
- 성공한 Command **하나당** `graphVersion`은 정확히 한 번,
  `expectedGraphVersion + 1`로 증가한다. 삭제 Node 수와 무관하다.

`currentGraphVersion != expectedGraphVersion`이면 graph mutation 없이
`GRAPH_VERSION_CONFLICT`로 reject한다. 검사 전에 `project_graph_state` row를
`FOR UPDATE`로 잠그므로 같은 `expectedGraphVersion`을 쓴 동시 mutation 중 하나만
성공한다.

`project_graph_state` row 부재는 시스템 전체에서 `graphVersion = 0`을 뜻한다. graph가
한 번도 바뀐 적 없는 project는 잠글 row가 없으므로 version 0 row를 먼저
materialize한 뒤 잠근다. 이 row는 lock을 걸기 위한 발판일 뿐 영속 사실이 아니다.

- 삭제 성공 → `bump_graph_version`이 같은 row를 0에서 1로 올리고 commit한다.
- Business rejection → 이번 transaction이 만든 row는 commit 전에 지운다. 따라서
  rejection 후에도 project는 row가 없는 상태 그대로이며
  `/internal/projects/{id}/graph-snapshot`의 404/absence 의미가 바뀌지 않는다.
- 이미 row가 있던 project는 rejection에서 그 row를 읽기만 하고 건드리지 않는다.

`INSERT ... ON CONFLICT DO NOTHING RETURNING`이 row를 돌려줄 때만 "이번 transaction이
만들었다"로 판정하므로, 먼저 insert한 동시 transaction의 row를 우리 것으로 오인해
지우는 일은 없다.

## 논리 삭제

물리 DELETE는 하지 않는다. Node/Evidence/NodeRevision/MergeOperation/
NodeAnalysisRun 어느 것도 지우지 않는다. 기존 soft delete 컬럼을 그대로 쓴다.

```text
graph_state      = 'DELETED'
deleted_at       = now
deleted_by       = requestedByMemberId
parent_id        = NULL
merged_into_node_id = NULL
last_actor_type  = 'USER'
```

`ck_node_deleted_shape`와 `ck_node_merge_shape`가 `DELETED` row의 merge pointer를
NULL로 요구하므로 pointer를 먼저 지우고 state를 바꾼다. 기존 user delete와 동일하게
`CONFIRMED` Relation은 `REJECTED` + `valid_to = now`로 만료시키고 embedding은 stale로
표시하며 `USER_DELETE_NODE`/`USER_DELETE_MERGED` GraphChangeEvent를 남긴다.

## Transaction

한 transaction에서 다음이 모두 commit되거나 아무것도 commit되지 않는다.

```text
commandId 멱등 검사 → project_graph_state FOR UPDATE → expectedGraphVersion 검증
→ seed 조회/검증 → closure 계산 → invariant 검증 → 논리 삭제(nodeVersion +1)
→ graphVersion +1 → Full Graph Snapshot v1 freeze → GraphSnapshotArtifact
→ PROJECT_GRAPH_CHANGED Result Outbox → command outcome
```

Domain transaction 안에서 S3나 SQS를 호출하지 않는다. commit 이후 Input Command를
ACK하고, 기존 Outbox Publisher가 artifact를 S3에 올린 뒤 Result SQS로 보낸다.
commit 이후 graph를 다시 읽어 Snapshot을 재조립하지 않는다. transaction 안에서
고정한 immutable artifact를 그대로 발행한다.

## 성공 Result Event

기존 Result Event v3와 claim-check 구조를 그대로 쓴다.

```json
{
  "sourceType": "NODE_DELETE",
  "graphVersion": 13,
  "snapshotRef": {
    "bucket": "configured-result-bucket",
    "objectKey": "graph-snapshots/project-1/command-<uuid>/v13.json",
    "contentType": "application/json",
    "sizeBytes": 12345,
    "sha256": "lowercase-hex"
  }
}
```

`eventType`은 `PROJECT_GRAPH_CHANGED`, `meetingId`는 `null`이다. Snapshot은
`deleted_at IS NULL`인 `ACTIVE`/`UNATTACHED`/`MERGED` Node와 그 Evidence, 살아 있는
`MERGED` source의 merge record만 담는다. 과거 `deletedNodes` delta event 경로는
사용하지 않는다.

## Business rejection

```json
{
  "sourceType": "NODE_DELETE",
  "reasonCode": "GRAPH_VERSION_CONFLICT"
}
```

`eventType`은 `NODE_DELETE_REJECTED`, `meetingId`는 `null`이다. payload는 Java Node
Delete 계약이 합의한 두 field만 담는다. seed `nodeIds`와 관측된 graph version은
command inbox row(`expected_graph_version`, `failure_message`)와 change log에 남으므로
진단에는 쓸 수 있지만 wire 계약을 넓히지 않는다. `reasonCode`는 다음 중 하나다.

- `GRAPH_VERSION_CONFLICT`
- `NODE_NOT_FOUND`
- `NODE_PROJECT_MISMATCH`

rejection도 `FAILED` outcome과 같은 transaction에서 Outbox에 저장하므로 Result SQS
장애는 기존 Outbox retry가 처리한다. `NODE_DELETE_SET_INCOMPLETE`는 parent 자동
cascade 정책으로 대체되었고 이 경로에서 발생하지 않는다.

Infrastructure 실패는 business rejection으로 바꾸지 않는다. Snapshot 크기 초과는
transaction을 rollback하고 `GRAPH_SNAPSHOT_TOO_LARGE` outcome만 기록하며 Result
event를 만들지 않는다.

## 멱등성

- 같은 `commandId` + 같은 payload → graph를 다시 바꾸지 않고 `graphVersion`도 다시
  올리지 않으며 기존 outcome·artifact·event를 그대로 재사용한다. `eventId`는 안정적이다.
- 같은 `commandId` + 다른 payload → `COMMAND_ID_PAYLOAD_CONFLICT`, graph mutation 없음.

payload hash는 Java가 보낸 `nodeIds` 순서까지 포함한다. 순서가 다르면 다른 payload다.
중복 제거는 처리 단계에서만 한다.

## Follow-up issue (이번 작업 범위 밖)

`complete_initial_review`는 Java Snapshot에 포함되는 `UNATTACHED` Node를 만들면서
graphVersion을 올리지 않는다.

```text
complete_initial_review
  → UNATTACHED Node 생성
  → GraphChangeEvent audit
  → commit
  → graphVersion bump 없음
  → GraphSnapshotArtifact 없음
  → PROJECT_GRAPH_CHANGED Result Outbox 없음
```

live path 두 개가 여기에 도달한다.

- `POST /api/v1/candidates/{id}/approve`
- `POST /api/v1/meetings/{id}/initial-review/complete`

후속 단계도 bump하지 않는다. `_queue_analysis_for_meeting`은
`INITIAL_REVIEW_READY`를 schema `v2.2`로 발행하는데 `result-sqs` publisher는 schema
`3` row만 claim하므로 Java Result Queue에 닿지 않는다. Analysis Worker에도 bump 호출이
없다.

결과적으로 Java projection에 반영되어야 할 Node가 아무 신호 없이 늘어나고, 이후
무관한 mutation이 v+1 Snapshot에 그 Node들을 한꺼번에 실어 나른다. Full replace라
Java는 수렴하지만 graphVersion이 Snapshot 내용 변화의 정직한 카운터가 아니다. 이
상태가 "Node은 있는데 `project_graph_state` row는 없는" project의 발생원이기도 하다.

이번 Node Delete 작업에서는 고치지 않는다. 초기 검토 Node 생성을 Java로 발행할 때의

- `sourceType`
- `commandId` correlation
- `meetingId` correlation
- Java가 `UNATTACHED`를 즉시 Projection에 반영해야 하는지

가 아직 계약으로 확정되지 않았기 때문이다. `sourceType=MEETING_ANALYSIS`나
`sourceType=INITIAL_REVIEW` 같은 값을 임의로 만들지 않는다. Java/Python 계약 결정이
선행되어야 한다.

자동 그래프 경로(`MEETING_ANALYSIS_REQUESTED` → `automatic_graph`)는 Node 생성과
bump가 같은 transaction이므로 이 gap이 없다.
