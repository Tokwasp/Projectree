# Node content update API and SQS contract

## End-to-end flow

Java validates the request and current projection version, stores a command in the existing
`meeting_analysis_command_outbox`, and returns `202 Accepted`. The existing publisher sends the
outbox payload to the existing meeting-analysis queue. Python owns the authoritative node update,
optimistic concurrency check, protected-field policy, snapshot creation, and result publication.
Java never changes `ProjectNodeProjection` during the PATCH transaction; it replaces the projection
only after receiving and validating a newer snapshot.

## PATCH API

`PATCH /api/projects/{projectId}/nodes/{nodeId}`

Only one graph-changing command may be active per project. When another
meeting-analysis, node-update, or node-delete command owns the project guard,
this endpoint returns `409 Conflict` with error code
`GRAPH_OPERATION_IN_PROGRESS`.

Request:

```json
{
  "title": "JWT 인증 방식 결정",
  "content": "Access Token과 Refresh Token을 사용하기로 결정했다.",
  "expectedNodeVersion": 3
}
```

`expectedNodeVersion` is required and positive. At least one of `title` and `content` is required.
Provided values cannot be blank. Title is stripped and limited to 255 characters; content is
preserved verbatim and limited to 65,535 characters.

Accepted response:

```json
{
  "status": 202,
  "message": "성공",
  "data": {
    "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
    "nodeId": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "expectedNodeVersion": 3,
    "status": "PENDING"
  }
}
```

## Command message

The SQS message body is the outbox payload. The `commandId` message attribute contains the same
UUID. Unmodified title or content is JSON `null`.

```json
{
  "commandSchemaVersion": 1,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
  "requestedAt": "2026-08-06T06:30:00Z",
  "projectId": 1,
  "payload": {
    "nodeId": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
    "expectedNodeVersion": 3,
    "title": "JWT 인증 방식 결정",
    "content": "Access Token과 Refresh Token을 사용하기로 결정했다.",
    "requestedByMemberId": 15
  }
}
```

## Result event

The current Java result envelope schema version is `3`. Node update results reuse
`PROJECT_GRAPH_CHANGED`; both event and snapshot `meetingId` values must be JSON `null`.

```json
{
  "eventSchemaVersion": 3,
  "eventId": "792cbf87-b2ed-4010-a893-beb286597a47",
  "eventType": "PROJECT_GRAPH_CHANGED",
  "occurredAt": "2026-08-06T06:30:02Z",
  "projectId": 1,
  "meetingId": null,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "payload": {
    "sourceType": "NODE_CONTENT_UPDATE",
    "graphVersion": 12,
    "snapshotRef": {
      "bucket": "configured-graph-bucket",
      "objectKey": "graph-snapshots/project-1/version-12.json",
      "contentType": "application/json",
      "sizeBytes": 12345,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }
}
```

Snapshot:

```json
{
  "snapshotSchemaVersion": 1,
  "projectId": 1,
  "meetingId": null,
  "commandId": "e4f3e557-e52d-40ef-90ef-420175659413",
  "graphVersion": 12,
  "generatedAt": "2026-08-06T06:30:02Z",
  "nodes": [
    {
      "nodeId": "0afdda91-2576-54d3-bb87-8e9263b1d17c",
      "nodeVersion": 4,
      "title": "JWT 인증 방식 결정",
      "content": "Access Token과 Refresh Token을 사용하기로 결정했다."
    }
  ],
  "evidences": [],
  "mergeRecords": []
}
```

## Versioning, retries, and idempotency

`expectedNodeVersion` protects one authoritative node update in Python. Java's early comparison only
rejects already-stale requests; two requests based on the same projection version may both be
queued, and Python must resolve the final conflict atomically.

For a newer node-update graph snapshot, Java requires the target node to be present, its
`nodeVersion` to be greater than `expectedNodeVersion`, and every non-null requested title/content
field to match the snapshot. A contract violation rolls back both Inbox registration and projection
replacement.

`graphVersion` orders whole-project snapshots. Java replaces projections only when the received
version is greater than `ProjectGraphSync.currentGraphVersion`. `commandId` uniquely identifies a
command and `eventId` uniquely identifies a result, so redelivery is idempotent.

Transport failures and temporary storage/database failures are retryable. Invalid schemas,
references, hashes, source/command combinations, or version-conflict command outcomes are
non-retryable contract/business failures. Node-update publish failure does not modify a Meeting or
create meeting-analysis notifications. Logs must not include the command payload, title, or content.

## Current final-result limitation

`202 Accepted` with `PENDING` means only that Java accepted and staged the SQS command. It does not
mean that the Python database update succeeded. Python owns the final concurrency decision, but
there is currently no Java result contract for Python-side version conflicts, missing/deleted
targets, non-retryable database errors, or protected-field policy failures.

The frontend can currently confirm success only after `PROJECT_GRAPH_CHANGED` has been applied and
the updated graph is visible through a subsequent query. Returning a user-visible failure reason
requires a follow-up contract such as `NODE_CONTENT_UPDATE_REJECTED`,
`NODE_CONTENT_UPDATE_FAILED`, or a command-status query API. Those features are intentionally
outside this implementation.
