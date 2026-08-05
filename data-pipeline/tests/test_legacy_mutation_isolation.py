from __future__ import annotations

import uuid

import pytest

from data_pipeline.pipeline import (
    LegacyGraphMutationDisabledError,
    apply_change_plan,
    approve_candidate,
    bulk_approve_candidates,
    process_request,
)
from data_pipeline.storage import Node, Relation


def test_legacy_graph_mutation_entry_points_are_blocked_by_default(
    monkeypatch,
    session_factory,
):
    monkeypatch.delenv(
        "DATA_PIPELINE_UNSAFE_ENABLE_LEGACY_GRAPH_MUTATION_FOR_TESTS",
        raising=False,
    )

    with pytest.raises(LegacyGraphMutationDisabledError):
        process_request(session_factory, {})
    with pytest.raises(LegacyGraphMutationDisabledError):
        apply_change_plan(None, None, None)
    with pytest.raises(LegacyGraphMutationDisabledError):
        approve_candidate(
            session_factory,
            uuid.uuid4(),
            actor_id="caller",
        )
    with pytest.raises(LegacyGraphMutationDisabledError):
        bulk_approve_candidates(
            session_factory,
            [uuid.uuid4()],
            actor_id="caller",
        )

    with session_factory() as session:
        assert session.query(Node).count() == 0
        assert session.query(Relation).count() == 0
