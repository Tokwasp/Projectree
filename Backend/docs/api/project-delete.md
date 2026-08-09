# Project deletion API

Explicit deletion:

```http
DELETE /api/projects/{projectId}
```

Owner-leave deletion:

```http
DELETE /api/projects/{projectId}/members/me
```

After project and requester authorization checks, both project-deleting paths
lock `ProjectGraphSync` with `PESSIMISTIC_WRITE`.

- Active graph operation: `409 GRAPH_OPERATION_IN_PROGRESS`
- Missing `ProjectGraphSync`: internal `PROJECT_GRAPH_SYNC_NOT_FOUND`
- Idle project: members, Sync state, and project are deleted atomically

An ordinary non-owner member leave removes only that member and does not delete
the project or its Sync state.
