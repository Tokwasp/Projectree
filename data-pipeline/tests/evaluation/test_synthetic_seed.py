from __future__ import annotations

from sqlalchemy import func, select

from data_pipeline.evaluation.synthetic.labels import build_gold_labels
from data_pipeline.evaluation.synthetic.scenarios import (
    ISOLATION_PROJECT_ID,
    MAIN_PROJECT_ID,
    build_synthetic_cases,
)
from data_pipeline.evaluation.synthetic.seed import seed_synthetic_evaluation
from data_pipeline.storage import (
    Evidence,
    Node,
    NodeRevision,
    NodeRevisionEvidence,
)


def test_synthetic_scenarios_have_confirmed_predeclared_labels():
    cases = build_synthetic_cases()
    labels = build_gold_labels(cases)

    assert len(cases) == 40
    assert len({case.case_id for case in cases}) == 40
    assert all(label.label_status.value == "CONFIRMED" for label in labels)
    assert sum(label.expected_action == "MERGE" for label in labels) >= 15
    assert sum(label.category == "hard-negative" for label in labels) >= 10


def test_synthetic_seed_is_idempotent_and_revision_complete(session_factory):
    db_session = session_factory()
    try:
        first = seed_synthetic_evaluation(db_session)
        db_session.commit()
        second = seed_synthetic_evaluation(db_session)
        db_session.commit()

        assert first.main_node_count == 90
        assert first.isolation_node_count == 8
        assert first.gold_case_count == 40
        assert second.created_nodes == 0
        assert second.reused_nodes == 98
        assert second.created_relations == 0

        nodes = list(
            db_session.execute(
                select(Node).where(
                    Node.project_id.in_(
                        (MAIN_PROJECT_ID, ISOLATION_PROJECT_ID)
                    )
                )
            ).scalars()
        )
        assert all(node.current_revision_id is not None for node in nodes)
        assert all(
            db_session.get(NodeRevision, node.current_revision_id) is not None
            for node in nodes
        )
        evidence_links = db_session.execute(
            select(func.count(NodeRevisionEvidence.evidence_id))
        ).scalar_one()
        evidence_count = db_session.execute(
            select(func.count(Evidence.id))
        ).scalar_one()
        assert evidence_links >= 98
        assert evidence_count >= 98
    finally:
        db_session.close()
