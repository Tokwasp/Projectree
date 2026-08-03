# Graph category cascade and soft delete

## Category change

A Decision can change category without a structural parent. Its ACTIVE
descendant subtree changes category in the same transaction. An Action or
Issue category change must include `newParentNodeId`; the parent must be an
ACTIVE canonical Node in the same project and new category, with a valid type.
Missing/invalid parents and cycles roll back the complete request. No automatic
UNATTACHED fallback is allowed. Each changed Node gets a new immutable revision
and version. Category-only changes keep READY embeddings because category is
not part of embedding contract v2.

An ACTIVE canonical merge target may be changed. MERGED sources and merge
history are not rewritten.

## Soft delete

Only ACTIVE and UNATTACHED Nodes can be soft-deleted. MERGED sources and
canonical targets with applied incoming merges require unmerge first. The
transaction creates a final revision, sets `graph_state=DELETED`, `deleted_at`
and `deleted_by`, invalidates the deleted Node's embedding, ends its relations,
and detaches every structurally affected descendant as UNATTACHED with a new
revision/version. No graph history, revision, evidence, merge, or analysis row
is physically deleted.

Deleted Nodes are excluded from reads, retrieval, parents, merge targets,
Snapshots and embedding backfill. The graph event puts the deleted Node in
`deletedNodes` and affected descendants in `upsertedNodes`.
