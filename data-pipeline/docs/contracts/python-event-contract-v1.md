# Python Event Contract v1

Python PostgreSQL is the graph source of truth. Spring consumes the
transactional outbox with at-least-once delivery and deduplicates by the stable
`eventId`. Java HTTP transmission is intentionally outside this repository.

The envelope is `eventSchemaVersion`, `eventId`, `eventType`, `occurredAt`
(UTC `Z`), `projectId`, and `payload`. Numeric signed-64-bit identifiers are
JSON numbers; UUIDs and external room identifiers remain strings.

Supported events:

- `PROJECT_GRAPH_CHANGED`: `projectId`, monotonic `graphVersion`, complete
  `upsertedNodes`, and `deletedNodes`. A mutation transaction increments the
  version exactly once and writes the outbox row atomically.
- `MEETING_SUMMARY_READY` (legacy no-command path only): summary identity/version/status and an `apiPath`; command-based SUMMARY success uses the Java HTTP Callback instead.
  the full summary body is never duplicated into the event.
- `ANALYSIS_STATUS_CHANGED`: `PROCESSING`, `SUCCEEDED`, or `FAILED`.
  `SUCCEEDED` is emitted only after both the graph and meeting summary are
  ready and includes `requiredGraphVersion` and `requiredSummaryVersion`.

Event Node evidence excludes `startMs` by the current Java handoff policy.
Python's transcript/evidence storage and ordinary graph API retain it.

Golden payloads live in `docs/contracts/fixtures/event-v1/` and are verified
against the real serializer in `tests/test_event_v1_fixtures.py`.
