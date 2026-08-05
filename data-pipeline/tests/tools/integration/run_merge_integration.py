"""Exercise initial review, Retrieval, B recommendation, and merge approval.

This diagnostic uses deterministic fake Embedding/B-model adapters while
calling the real service boundaries and PostgreSQL constraints. It requires a
disposable ``dp_test_*`` database and an already successful generation request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import selectinload

from data_pipeline.config import load_settings
from data_pipeline.pipeline import (
    approve_merge_existing,
    complete_initial_review,
    execute_analysis_retrieval,
    execute_b_model,
    reanalyze_unattached_node,
    seed_node,
)
from data_pipeline.storage import (
    AnalysisCandidate,
    GraphChangeEvent,
    Node,
    NodeCandidate,
    NodeEmbedding,
    NodeEvidence,
    NodeMergeHistory,
    Relation,
    make_engine,
    make_session_factory,
)


class DeterministicEmbeddingClient:
    def embed(self, *, text: str, model: str, dimensions: int) -> list[float]:
        del text, model
        return [1.0, *([0.0] * (dimensions - 1))]


class DeterministicMergeClient:
    def __init__(self, target_id, *, title: str, content: str):
        self._target_id = target_id
        self._title = title
        self._content = content

    def recommend(self, *, source_node: dict, retrieval_candidates: list[dict], model: str):
        del source_node, model
        target_ids = {value["nodeId"] for value in retrieval_candidates}
        if str(self._target_id) not in target_ids:
            raise RuntimeError("seeded merge target was not retrieved")
        return {
            "recommendation": "MERGE",
            "targetNodeId": str(self._target_id),
            "relationType": None,
            "suggestedTitle": self._title,
            "suggestedContent": self._content,
            "reason": "deterministic integration merge candidate",
            "metadata": {"adapter": "deterministic-integration-v1"},
        }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--meeting-id", required=True)
    parser.add_argument("--source-item-id", default="m21")
    parser.add_argument("--actor-id", default="integration-reviewer")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    database_url = os.getenv("DATABASE_URL", "")
    database_name = make_url(database_url).database or ""
    if not database_name.startswith("dp_test_"):
        raise RuntimeError(
            "Merge integration requires a disposable dp_test_* database"
        )
    load_settings.cache_clear()
    retrieval = load_settings().retrieval
    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)
    try:
        with session_factory() as session:
            candidates = session.execute(
                select(NodeCandidate)
                .where(
                    NodeCandidate.project_id == args.project_id,
                    NodeCandidate.external_meeting_id == args.meeting_id,
                )
                .order_by(NodeCandidate.source_item_id)
            ).scalars().all()
        if not candidates:
            raise RuntimeError("No generated candidates were found")

        created_node_ids: list[str] = []
        for candidate in candidates:
            result = complete_initial_review(
                session_factory,
                candidate.id,
                project_id=args.project_id,
                actor_id=args.actor_id,
                expected_version=candidate.version,
            )
            created_node_ids.extend(result.created_node_ids)

        vector = [1.0, *([0.0] * (retrieval.embedding_dim - 1))]
        with session_factory() as session:
            source = session.execute(
                select(Node)
                .options(selectinload(Node.evidence))
                .where(
                    Node.project_id == args.project_id,
                    Node.source_meeting_id == args.meeting_id,
                    Node.source_item_id == args.source_item_id,
                )
            ).scalar_one()
            target = seed_node(
                session,
                project_id=args.project_id,
                source_meeting_id="integration-seed-meeting",
                source_item_id="integration-merge-target",
                node_type=source.node_type,
                category=source.category,
                title="기존 EC2 기반 개인 기능 운영 결정",
                content=(
                    "개인 기능은 EC2에서 운영하고 RDS 접근도 EC2 경유로 "
                    "구성한다."
                ),
                graph_state="ACTIVE",
                evidence=[
                    {
                        "segmentId": "seed-segment-1",
                        "quote": "개인 기능 운영에는 EC2를 사용한다.",
                    }
                ],
            )
            session.add(
                NodeEmbedding(
                    node_id=target.id,
                    embedding_version=retrieval.embedding_version,
                    embedding_model=retrieval.embedding_model,
                    dimension=retrieval.embedding_dim,
                    embedded_text_hash="integration-seed",
                    embedding=vector,
                    status="READY",
                    embedded_at=datetime.now(timezone.utc),
                )
            )
            source_id = source.id
            source_version = source.version
            target_id = target.id
            source_title = source.title
            source_content = source.content
            session.commit()

        requested = reanalyze_unattached_node(
            session_factory,
            source_id,
            project_id=args.project_id,
            actor_id=args.actor_id,
            expected_version=source_version,
        )
        retrieval_result = execute_analysis_retrieval(
            session_factory,
            requested.run.analysis_run_id,
            project_id=args.project_id,
            embedding_client=DeterministicEmbeddingClient(),
        )
        merged_title = "개인 기능 EC2 운영 및 RDS 접근 결정"
        merged_content = (
            source_content
            + "\n기존 결정과 통합하여 개인 기능과 RDS 접근 경로를 "
            "EC2 기준으로 운영한다."
        ).strip()
        recommendation = execute_b_model(
            session_factory,
            requested.run.analysis_run_id,
            project_id=args.project_id,
            client=DeterministicMergeClient(
                target_id,
                title=merged_title,
                content=merged_content,
            ),
            model="deterministic-integration-b",
            model_version="v1",
        )
        if recommendation.candidate is None:
            raise RuntimeError("B-model merge candidate was not created")
        approval = approve_merge_existing(
            session_factory,
            recommendation.candidate.candidate_id,
            project_id=args.project_id,
            actor_id=args.actor_id,
            expected_version=recommendation.candidate.version,
        )

        with session_factory() as session:
            source = session.get(Node, source_id)
            target = session.get(Node, target_id)
            target_embedding = session.get(
                NodeEmbedding,
                {
                    "node_id": target_id,
                    "embedding_version": retrieval.embedding_version,
                },
            )
            summary = {
                "projectId": args.project_id,
                "meetingId": args.meeting_id,
                "reviewedCandidateCount": len(candidates),
                "createdUnattachedNodeCount": len(created_node_ids),
                "sourceNodeId": str(source_id),
                "sourceOriginalTitle": source_title,
                "targetNodeId": str(target_id),
                "retrievalResultCount": len(retrieval_result.retrieval_results),
                "retrievedTargetIds": [
                    value.target_node_id
                    for value in retrieval_result.retrieval_results
                ],
                "analysisCandidateId": recommendation.candidate.candidate_id,
                "mergeHistoryId": approval.merge_history_id,
                "sourceGraphState": source.graph_state,
                "sourceMergedIntoNodeId": str(source.merged_into_node_id),
                "targetGraphState": target.graph_state,
                "targetTitle": target.title,
                "targetVersion": target.version,
                "targetEmbeddingStatus": target_embedding.status,
                "sourceEvidenceCount": session.scalar(
                    select(func.count())
                    .select_from(NodeEvidence)
                    .where(NodeEvidence.node_id == source_id)
                ),
                "targetOwnEvidenceCount": session.scalar(
                    select(func.count())
                    .select_from(NodeEvidence)
                    .where(NodeEvidence.node_id == target_id)
                ),
                "mergeHistoryCount": session.scalar(
                    select(func.count()).select_from(NodeMergeHistory)
                ),
                "relationCount": session.scalar(
                    select(func.count()).select_from(Relation)
                ),
                "analysisCandidateCount": session.scalar(
                    select(func.count()).select_from(AnalysisCandidate)
                ),
                "graphChangeEventCount": session.scalar(
                    select(func.count()).select_from(GraphChangeEvent)
                ),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
