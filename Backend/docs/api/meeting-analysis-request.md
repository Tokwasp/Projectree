# Meeting analysis request API

`PUT /api/projects/{projectId}/meetings/{roomName}/analysis-request`

## Task selection

```json
{
  "generateSummary": true,
  "generateNodes": true
}
```

| generateSummary | generateNodes | Accepted | Project graph guard |
|---|---|---|---|
| `true` | `true` | yes | acquired |
| `true` | `false` | yes | not acquired |
| `false` | `true` | yes | acquired |
| `false` | `false` | yes | not acquired |

Both fields are required.

`false / false` is a valid explicit selection. It means that the user
confirmed that neither summary generation nor node generation is requested.

The meeting stores both task statuses as `SKIPPED`, while a
`MEETING_ANALYSIS_REQUESTED` command is still staged in the outbox with both
flags set to `false`.

Because node generation is not requested, this combination does not acquire
the project graph operation guard.

Summary-only analysis does not change Graph Projection or Graph Version. It is
therefore allowed while another graph-changing command owns the project guard.
Requests containing node generation return
`409 GRAPH_OPERATION_IN_PROGRESS` when the project guard is active.

## Guard lifecycle

- `MEETING_SUMMARY_READY` never releases the guard.
- `SUMMARY` terminal failure never releases the guard.
- Successful `PROJECT_GRAPH_CHANGED / MEETING_ANALYSIS` processing releases
  the guard after snapshot validation and projection replacement.
- `NODES` terminal failure releases the guard in its result transaction.
- Final command publish failure releases only when the immutable failed
  command payload requested node generation.
