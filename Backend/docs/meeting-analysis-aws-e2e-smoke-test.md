# Meeting analysis AWS E2E smoke test

This opt-in test verifies the full transport and Java projection path using real AWS SQS/S3 and an H2 test database.

## Flow

1. Java creates a meeting-analysis request and Command Outbox.
2. Java publishes `MEETING_ANALYSIS_REQUESTED` to the configured Command Queue.
3. The test acts as the Python worker and consumes that exact command.
4. The fake worker uploads a complete graph snapshot under `graph-snapshots/aws-e2e/...`.
5. The fake worker sends `MEETING_SUMMARY_READY` and `PROJECT_GRAPH_CHANGED` to the Result Queue.
6. The real Java Result Consumer receives both events, downloads the snapshot, and updates Summary/Graph Projections.
7. The test verifies Meeting statuses, Inbox entries, graph version, nodes, evidences, and tree query.
8. The test removes its S3 object and any remaining messages that contain its own IDs.

## Safety prerequisites

- Stop the real Python Command Queue consumer.
- Stop any separately running Java Result Queue consumer.
- Ensure both configured queues are empty. The test aborts if either queue is not empty.
- Use a development/staging queue and bucket, not production.
- The IAM principal used by the test needs:
  - Command Queue: `sqs:SendMessage`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes`
  - Result Queue: `sqs:SendMessage`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes`
  - Snapshot bucket/prefix: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`

## Required `.env` values

```env
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# AWS_SESSION_TOKEN=... # only for temporary credentials

MEETING_ANALYSIS_COMMAND_QUEUE_URL=https://sqs.ap-northeast-2.amazonaws.com/.../projectree-meeting-analysis-command
AWS_ANALYSIS_RESULT_QUEUE_URL=https://sqs.ap-northeast-2.amazonaws.com/.../projectree-analysis-result-dev
AWS_ANALYSIS_RESULT_BUCKET=projectree-bucket
MEETING_ANALYSIS_GRAPH_SNAPSHOT_S3_PREFIX=graph-snapshots/
```

Spring's `.env` import alone does not populate operating-system environment variables. The PowerShell runner exports `.env` values into the Gradle test process so AWS SDK `DefaultCredentialsProvider` can read them.

## Run on Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-meeting-analysis-aws-e2e-smoke.ps1
```

Normal `gradlew test` does not execute this test because it carries the `smoke` tag.
