"""Same-meeting parent hints for the analysis stage.

During generation the judgment stage may propose that an ACTION/ISSUE belongs
under a DECISION from the *same meeting* (``suggested_parent_candidate_id``).
That knowledge must survive to final analysis: the approved parent Node is
force-included in the Retrieval candidate set so the B model can see it even
when it is not in the vector Top-K yet (a freshly created parent usually has no
embedding at all).

The hint never auto-attaches anything. It only widens the candidate set and is
flagged in the B-model input; the user still makes the final decision.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from data_pipeline.storage import Node, NodeCandidate

#: Bounded follow of merged_into chains so a hint cannot loop forever.
_MAX_MERGE_HOPS = 5

#: Graph states a hint target may have. Mirrors the Retrieval filter.
_ALLOWED_HINT_STATES = frozenset({"ACTIVE", "UNATTACHED"})


@dataclass(frozen=True)
class ParentHint:
    """A same-meeting parent proposal resolved to a live Node."""

    node_id: uuid.UUID
    node_version: int
    origin: str  # "SAME_MEETING_CANDIDATE" | "SUGGESTED_NODE"


def _effective_parent_ids(
    candidate: NodeCandidate,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Reviewer override wins over the LLM suggestion (mirrors review._effective_parent)."""

    mode = candidate.reviewed_parent_mode or "INHERIT"
    if mode == "INHERIT":
        return (
            candidate.suggested_parent_candidate_id,
            candidate.suggested_parent_node_id,
        )
    if mode == "CANDIDATE":
        return candidate.reviewed_parent_candidate_id, None
    if mode == "NODE":
        return None, candidate.reviewed_parent_node_id
    # "NONE" or anything unknown: the reviewer explicitly cleared the parent.
    return None, None


def _canonical(session, node: Node | None) -> Node | None:
    """Follow merged_into to the canonical target, bounded."""

    hops = 0
    while node is not None and node.merged_into_node_id is not None:
        hops += 1
        if hops > _MAX_MERGE_HOPS:
            return None
        node = session.get(Node, node.merged_into_node_id)
    return node


def resolve_same_meeting_parent_hint(
    session,
    source_node: Node,
) -> ParentHint | None:
    """Resolve the source Node's candidate-stage parent proposal, or None.

    The hint is discarded (returns None) when:
    - the source Node was not created from a candidate,
    - the reviewer cleared the parent (mode NONE),
    - the parent candidate was rejected or never produced a Node,
    - the parent Node belongs to another project,
    - the canonical parent is not ACTIVE/UNATTACHED,
    - the parent resolves to the source Node itself.
    """

    if source_node.source_candidate_id is None:
        return None
    candidate = session.get(NodeCandidate, source_node.source_candidate_id)
    if candidate is None:
        return None

    parent_candidate_id, parent_node_id = _effective_parent_ids(candidate)

    parent: Node | None = None
    origin = ""
    if parent_candidate_id is not None:
        parent_candidate = session.get(NodeCandidate, parent_candidate_id)
        if (
            parent_candidate is None
            or parent_candidate.review_status != "APPROVED"
            or parent_candidate.initial_review_node_id is None
        ):
            return None
        parent = session.get(Node, parent_candidate.initial_review_node_id)
        origin = "SAME_MEETING_CANDIDATE"
    elif parent_node_id is not None:
        parent = session.get(Node, parent_node_id)
        origin = "SUGGESTED_NODE"
    else:
        return None

    parent = _canonical(session, parent)
    if parent is None:
        return None
    if parent.project_id != source_node.project_id:
        return None
    if parent.id == source_node.id:
        return None
    if parent.graph_state not in _ALLOWED_HINT_STATES:
        return None
    return ParentHint(node_id=parent.id, node_version=parent.version, origin=origin)


__all__ = ["ParentHint", "resolve_same_meeting_parent_hint"]
