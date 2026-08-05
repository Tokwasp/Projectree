# Java Result Event v3

## 공통 envelope

모든 이벤트는 `eventSchemaVersion=3`, 안정적인 UUID `eventId`, `eventType`, UTC `occurredAt`, 숫자 `projectId`, 숫자 `meetingId`, UUID `commandId`, `payload`를 가진다. 전달은 at-least-once이며 Java Inbox는 `eventId`로 중복 제거한다.

성공 이벤트는 `MEETING_SUMMARY_READY`와 `PROJECT_GRAPH_CHANGED`뿐이다. 통합 성공 이벤트는 없다. 실패는 최종 retry 소진 시 `ANALYSIS_TASK_STATUS_CHANGED`로 보내며 `taskType=SUMMARY|NODES`, `status=FAILED`, 제한·정제된 failure code/message를 포함한다.

## Graph claim-check

Graph mutation, graph version 증가, deterministic Full Snapshot v1 artifact, Result outbox는 한 DB transaction이다. Snapshot은 삭제되지 않은 `ACTIVE`, `UNATTACHED`, `MERGED` Node와 현 revision Evidence, merge record를 안정 정렬해 canonical UTF-8 JSON으로 만들고 size와 SHA-256을 저장한다. lifecycle/embedding/LLM 원문은 포함하지 않는다.

Publisher는 artifact bytes와 DB checksum을 검증해 결정적 object key로 S3에 업로드한 뒤 queue에는 다음 참조만 보낸다.

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

`result-sqs` publisher는 schema v3 row만 claim한다. Standard queue에는 추가 SQS 필드를 보내지 않고, FIFO는 `MessageGroupId=projectId`, `MessageDeduplicationId=eventId`를 사용한다. S3 성공 후 SQS 실패 시 같은 key/bytes/eventId로 재시도한다.

## Python 환경변수

```text
AWS_REGION=ap-northeast-2
PROJECTREE_ANALYSIS_RESULT_QUEUE_URL=<Python에서 Java로 보내는 Result Queue>
PROJECTREE_ANALYSIS_RESULT_QUEUE_TYPE=STANDARD
AWS_S3_BUCKET=projectree-bucket
PROJECTREE_GRAPH_SNAPSHOT_PREFIX=graph-snapshots/
PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES=10485760
```

Python과 Java는 Snapshot 최대 크기를 정확히 `10,485,760` bytes(10 MiB)로
맞춘다. 제한은 metadata나 Python 문자열 길이가 아니라 S3에 업로드하고
`sizeBytes` 및 SHA-256 계산에 재사용하는 동일한 canonical UTF-8 JSON bytes에
적용한다. 경계값은 허용하며 이를 초과하면 graph 변경 transaction을 rollback해
artifact와 Result outbox를 만들지 않는다. Publisher도 S3 PutObject 전에 같은
제한을 재검증하므로 초과 Snapshot은 S3나 Result Queue로 전송되지 않는다.

OpenVidu Recording Queue(`RECORDING_READY_QUEUE_URL`)와 Java Command Queue(`ANALYSIS_COMMAND_QUEUE_URL`)는 Result Queue와 서로 다른 역할의 별도 Queue다.
