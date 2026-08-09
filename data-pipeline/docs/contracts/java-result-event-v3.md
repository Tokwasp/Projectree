# Java Result Event v3

## 공통 envelope

모든 Result event는 `eventSchemaVersion=3`, 안정적인 UUID `eventId`, `eventType`, UTC
`occurredAt`, 숫자 `projectId`, 숫자 또는 사후 Graph 명령의 `null`인 `meetingId`, UUID
`commandId`, `payload`를 가진다.
전달은 at-least-once이며 Java Inbox가 `eventId`로 중복을 제거한다.

Command 기반 성공 경로는 다음과 같이 분리한다.

- `NODES` 성공: Result SQS의 `PROJECT_GRAPH_CHANGED`
- `SUMMARY` 성공: Result event가 아니라 Java meeting-record HTTP Callback
- task 최종 실패: Result SQS의 `ANALYSIS_TASK_STATUS_CHANGED`
- V2 Node 제목 Batch 수정 거절: Result SQS의 `NODE_CONTENT_UPDATE_REJECTED`

따라서 command 기반 `SUMMARY` 성공에 `MEETING_SUMMARY_READY`를 발행하지 않는다. 이
상수와 stage 함수는 command가 없는 legacy 경로의 호환을 위해서만 남아 있다.

## 실패 event

최종 retry 소진 또는 재시도할 수 없는 실패는 다음 payload를 사용한다.

```json
{
  "taskType": "SUMMARY",
  "status": "FAILED",
  "failureCode": "SUMMARY_CALLBACK_DELIVERY_FAILED",
  "failureMessage": "제한되고 정제된 오류 메시지"
}
```

`taskType`은 `SUMMARY|NODES`, `status`는 `FAILED`다. 공통 `failureCode`는 non-blank
최대 100자, `failureMessage`는 non-blank 최대 1,000자다. Summary failure code는 다음 중
하나다.

- `SUMMARY_GENERATION_FAILED`
- `SUMMARY_CALLBACK_REJECTED`
- `SUMMARY_CALLBACK_DELIVERY_FAILED`

`MEETING_RECORD_SUMMARY_ALREADY_FAILED` 응답은 Java가 이미 실패를 확정한 상태이므로
동일 실패 event를 중복 생성하지 않는다.

V2 Node 제목 Batch 수정의 결정적 실패는 `NODE_CONTENT_UPDATE_REJECTED`를 사용한다.
특정 Node가 원인이면 `failedNodeId`에 canonical UUID를 넣는다. V2 `NO_CHANGE`는 첫
no-op Node UUID를 넣고, `GRAPH_SNAPSHOT_TOO_LARGE`처럼 특정 Node가 없는 Batch 전체
실패만 `null`을 넣는다. V1 단건 수정에는 호환성을 위해 이 rejection event를 소급
적용하지 않는다.

## Graph claim-check

Graph mutation, graph version 증가, deterministic Full Snapshot v1 artifact, Result outbox는
한 DB transaction이다. Snapshot은 삭제하지 않은 `ACTIVE`, `UNATTACHED`, `MERGED` Node와
그 revision Evidence 및 merge record를 안정 정렬한 canonical UTF-8 JSON으로 만들고,
size와 SHA-256을 저장한다. lifecycle/embedding/LLM 원문은 포함하지 않는다.

Publisher는 artifact bytes를 DB checksum과 검증해 결정적 object key로 S3에 업로드한 뒤
queue에는 다음 참조만 보낸다.

```json
{
  "sourceType": "MEETING_ANALYSIS",
  "graphVersion": 5,
  "snapshotRef": {
    "bucket": "configured-result-bucket",
    "objectKey": "graph-snapshots/project-5/command-command-uuid/v5.json",
    "contentType": "application/json",
    "sizeBytes": 843210,
    "sha256": "lowercase-hex"
  }
}
```

`result-sqs` publisher는 schema v3 row만 claim한다. Standard queue에는 추가 SQS 필드를
보내지 않고 FIFO면 `MessageGroupId=projectId`, `MessageDeduplicationId=eventId`를 사용한다.
S3 성공 후 SQS 실패 시 같은 key/bytes/eventId로 재시도한다.

## Python 환경변수

```text
AWS_REGION=ap-northeast-2
PROJECTREE_ANALYSIS_RESULT_QUEUE_URL=<Python에서 Java로 보내는 Result Queue>
PROJECTREE_ANALYSIS_RESULT_QUEUE_TYPE=STANDARD
AWS_S3_BUCKET=projectree-bucket
PROJECTREE_GRAPH_SNAPSHOT_PREFIX=graph-snapshots/
PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES=10485760
```

Python과 Java의 Snapshot 최대 크기는 `10,485,760` bytes(10 MiB)로 동일하다. 제한은
S3에 업로드하고 `sizeBytes` 및 SHA-256 계산에 사용하는 동일 canonical UTF-8 JSON bytes에
적용한다. 초과하면 graph transaction을 rollback하고 artifact와 Result outbox를 만들지 않는다.

OpenVidu Recording Queue, Java Command Queue, Java Result Queue는 서로 다른 역할의 별도 Queue다.
