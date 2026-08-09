# Project Graph Operation Guard

## Purpose

Java serializes graph-changing commands per project. A project may have at
most one active command, while different projects remain independent.

Guarded command types:

- `MEETING_ANALYSIS_REQUESTED` only when `generateNodes=true`
- `NODE_CONTENT_UPDATE_REQUESTED`
- `NODE_DELETE_REQUESTED`

Summary-only meeting analysis and read-only graph queries do not acquire the
guard.

A meeting-analysis request with both task options set to `false` is valid and
still stages a `MEETING_ANALYSIS_REQUESTED` command, but it does not acquire
the project graph operation guard because node generation is not requested.

## Persistence and locking

`project_graph_sync` owns the active operation fields:

```text
active_command_id   VARCHAR(36) nullable
active_command_type VARCHAR(50) nullable
active_since        DATETIME(6) nullable
```

All three values are either present together or `NULL` together. New projects
create their `ProjectGraphSync` row in the project creation transaction. The
manual migration backfills missing rows for existing projects.

Acquisition loads the project row with `PESSIMISTIC_WRITE`. Guard acquisition
and command/outbox persistence participate in the same caller transaction, so
an outbox failure rolls back the guard as well. A missing sync row is treated
as an internal consistency error and is never created by the acquisition path.

## Conflict contract

When a project already owns a guard, another graph-changing request fails with:

```http
409 Conflict
```

```text
GRAPH_OPERATION_IN_PROGRESS
```

The response does not need to expose the active command ID.

## Release policy

Release compares the completing `commandId` with `active_command_id`. A missing
or different ID never clears the current guard.

The guard is released in the same transaction after:

- a meeting-analysis graph snapshot is validated and its projection is applied;
- a node-content-update snapshot is validated and its projection is applied;
- a meeting-analysis `NODES` terminal `FAILED` result is persisted;
- a guarded command reaches final outbox publish failure.

Meeting-analysis publish failure parses the failed Outbox command payload.
It releases the guard only when that immutable payload has
`generateNodes=true`. Invalid payloads are internal contract failures and never
cause an arbitrary release.

Final `NODE_DELETE_REQUESTED` publish failure also marks the matching pending
`NodeDeleteCommand` as `FAILED` with `COMMAND_PUBLISH_FAILED` before release.

A duplicate result event is handled by the existing result inbox. A second
event for an already-applied command may be a no-op only when the incoming
graph version is not newer and `last_command_id` matches.

## Deliberate non-release cases

The guard is not released:

- on `MEETING_SUMMARY_READY` alone;
- on a `SUMMARY` failure while `NODES` is still processing;
- for summary-only publish failure, because no guard was acquired;
- before snapshot validation;
- when projection replacement fails or rolls back;
- for intermediate processing states;
- when a stale command ID does not own the current guard.

There is no time-based automatic release. Long-running guards must be observed
and handled operationally because delayed SQS results may still represent
authoritative Python work.

## Project deletion

Explicit project deletion and owner-leave deletion lock the
`ProjectGraphSync` row with `PESSIMISTIC_WRITE` and assert that the project is
idle. An active graph operation rejects deletion with
`409 GRAPH_OPERATION_IN_PROGRESS`; a missing Sync row is an internal
`PROJECT_GRAPH_SYNC_NOT_FOUND` consistency error.

After the idle check, deletion occurs in this order in the same transaction:

1. project members;
2. `ProjectGraphSync`;
3. project.

The lock prevents a concurrent graph command from acquiring the deleted
project while deletion is in progress. Non-owner member leave does not delete
the project and therefore does not require the project deletion guard.

## Node delete follow-up

The delete request service is not implemented yet. It must acquire
`NODE_DELETE_REQUESTED` and persist Pending Delete plus Outbox in the same
transaction. The future `NODE_DELETE_REJECTED` handler must update Pending
Delete visibility/state and release the guard atomically. The future delete
success projection applier must release only after full snapshot application.

## Logs

Guard lifecycle logs use the existing `[AnalysisFlow]` prefix:

- `GRAPH_OPERATION_GUARD_ACQUIRED`
- `GRAPH_OPERATION_GUARD_REJECTED`
- `GRAPH_OPERATION_GUARD_RELEASED`
- `GRAPH_OPERATION_GUARD_RELEASE_SKIPPED`
- `PROJECT_DELETE_BLOCKED_BY_GRAPH_OPERATION`

Logs contain identifiers, command type, timestamps, and release reason, but
never node title/content or the complete command payload.
