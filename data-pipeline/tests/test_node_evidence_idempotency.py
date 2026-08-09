from __future__ import annotations

from sqlalchemy import select

from data_pipeline.pipeline import seed_node
from data_pipeline.storage import (
    NodeEvidence,
    build_evidence_key,
    session_scope,
)


def _evidence(quote: str) -> dict:
    return {
        "segmentId": "s1",
        "quote": quote,
        "quoteStart": 0,
        "quoteEnd": len(quote),
    }


def test_seed_node_evidence_uses_stable_key_and_ignores_duplicate(session_factory):
    quote = "Redis를 캐시 저장소로 사용하기로 결정했습니다."
    with session_scope(session_factory) as session:
        node = seed_node(
            session,
            project_id="proj-01",
            source_meeting_id="M-EVIDENCE",
            source_item_id="d1",
            node_type="DECISION",
            category="BACKEND",
            title="Redis 결정",
            evidence=[_evidence(quote), _evidence(quote)],
        )
        node_id = node.id

    with session_factory() as session:
        rows = list(
            session.execute(
                select(NodeEvidence).where(NodeEvidence.node_id == node_id)
            ).scalars()
        )
        assert len(rows) == 1
        assert rows[0].evidence_key == build_evidence_key(
            segment_id="s1",
            quote=quote,
            quote_start=0,
            quote_end=len(quote),
            evidence_type="MEETING",
            source_meeting_id="M-EVIDENCE",
        )


def test_evidence_key_changes_when_normalized_quote_changes():
    common = {
        "segment_id": "s1",
        "quote_start": 0,
        "quote_end": 10,
        "evidence_type": "MEETING",
        "source_meeting_id": "M1",
    }

    assert build_evidence_key(quote="GitLab을 사용한다", **common) != (
        build_evidence_key(quote="GitHub를 사용한다", **common)
    )
