from __future__ import annotations

from data_pipeline.config import RetrievalSettings
from data_pipeline.evaluation.contracts import EvaluationCase
from data_pipeline.evaluation.runner import run_read_only_pilot
from data_pipeline.pipeline import seed_node
from data_pipeline.storage import NodeEmbedding
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION

DIMENSION = 1536
SETTINGS = RetrievalSettings(
    embedding_model="text-embedding-3-small",
    embedding_version=EMBEDDING_CONTRACT_VERSION,
    embedding_dim=DIMENSION,
    node_top_k=5,
)


def _seed(session, *, project: str, item: str, node_type="DECISION"):
    return seed_node(
        session,
        project_id=project,
        source_meeting_id="pilot-meeting",
        source_item_id=item,
        node_type=node_type,
        category="INFRA",
        title=f"pilot-{item}",
    )


def _embedding(session, node_id, vector):
    session.add(
        NodeEmbedding(
            node_id=node_id,
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            embedding_model="text-embedding-3-small",
            dimension=DIMENSION,
            embedded_text_hash="a" * 64,
            embedding=vector,
            status="READY",
        )
    )


def test_runner_uses_retrieval_and_changes_no_product_table(
    session_factory,
) -> None:
    vector = [1.0, *([0.0] * (DIMENSION - 1))]
    with session_factory() as session:
        source = _seed(session, project="pilot", item="source")
        target = _seed(session, project="pilot", item="target")
        other = _seed(session, project="other", item="other")
        _embedding(session, source.id, vector)
        _embedding(session, target.id, vector)
        _embedding(session, other.id, vector)
        session.commit()
        source_id = source.id
        target_id = target.id

    with session_factory() as session:
        results, verification = run_read_only_pilot(
            session,
            cases=[
                EvaluationCase(
                    caseId="case-001",
                    projectId="pilot",
                    sourceNodeId=source_id,
                    sourceNodeType="DECISION",
                )
            ],
            settings=SETTINGS,
        )

    assert verification["unchanged"] is True
    assert results[0].status == "COMPLETED"
    assert [row.node_id for row in results[0].candidates] == [target_id]
    assert results[0].candidates[0].type_valid is True


def test_runner_skips_source_without_ready_embedding(session_factory) -> None:
    with session_factory() as session:
        source = _seed(session, project="pilot", item="source")
        session.commit()
        source_id = source.id
    with session_factory() as session:
        results, verification = run_read_only_pilot(
            session,
            cases=[
                EvaluationCase(
                    caseId="case-001",
                    projectId="pilot",
                    sourceNodeId=source_id,
                )
            ],
            settings=SETTINGS,
        )
    assert results[0].reason == "READY_EMBEDDING_UNAVAILABLE"
    assert verification["unchanged"] is True
