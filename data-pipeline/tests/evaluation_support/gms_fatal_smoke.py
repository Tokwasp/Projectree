"""Safety helpers for the real-GMS production-orchestrator smoke test.

Nothing in this module substitutes production decisions.  It only meters the
existing adapters, creates/disposes an isolated PostgreSQL database, seeds a
small pre-existing graph, and inspects durable results.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, make_url

from data_pipeline.pipeline.user_graph import create_user_node
from data_pipeline.retrieval import (
    load_current_revision_embedding_input,
    validate_embedding,
)
from data_pipeline.storage import (
    AnalysisDeliveryState,
    BModelResult,
    Evidence,
    GenerationRun,
    MeetingSummary,
    MergeOperation,
    Node,
    NodeAnalysisRun,
    NodeCandidate,
    NodeEmbedding,
    NodeRevisionEvidence,
    OutboxEvent,
    ProjectGraphState,
    Relation,
    Request,
    RetrievalResult,
    TranscriptSegment,
)


PROJECT_ID = "9001"
OTHER_PROJECT_ID = "9002"
MEETING_ID = "gms-fatal-smoke-001"
PIPELINE_VERSION = "gms-fatal-smoke-v1"
RECORDING_HASH = hashlib.sha256(b"gms-fatal-smoke-001").hexdigest()

TRANSCRIPT_SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        "segmentId": "gms-smoke-segment-1",
        "sequenceNo": 1,
        "startMs": 0,
        "endMs": 11000,
        "speakerLabel": "PM",
        "text": "백엔드 로그인 인증은 기존 JWT 방식을 유지합니다. 세션 인증으로 전환하지 않습니다.",
    },
    {
        "segmentId": "gms-smoke-segment-2",
        "sequenceNo": 2,
        "startMs": 12000,
        "endMs": 23000,
        "speakerLabel": "Backend",
        "text": "JWT access token 재발급 API를 이번 스프린트에 구현하겠습니다.",
    },
    {
        "segmentId": "gms-smoke-segment-3",
        "sequenceNo": 3,
        "startMs": 24000,
        "endMs": 35000,
        "speakerLabel": "Backend",
        "text": "Access token 만료 시간과 refresh token 회전 정책은 아직 결정되지 않았습니다.",
    },
    {
        "segmentId": "gms-smoke-segment-4",
        "sequenceNo": 4,
        "startMs": 36000,
        "endMs": 47000,
        "speakerLabel": "Frontend",
        "text": "로그인 실패 화면에 표시할 오류 문구는 아직 결정되지 않았습니다.",
    },
)

_SECRET_FIELD = re.compile(
    r"(api[_-]?key|authorization|secret|gms[_-]?key|bearer)",
    re.IGNORECASE,
)


class SmokeBlocked(RuntimeError):
    pass


class FatalSmokeFailure(RuntimeError):
    pass


class HardCallBudgetExceeded(BaseException):
    """Escape production retry loops before an over-budget HTTP call occurs."""


@dataclass(frozen=True)
class CallBudget:
    max_candidate_calls: int = 2
    max_b_model_calls: int = 4
    max_embedding_items: int = 9
    max_http_requests: int = 15

    def validate(
        self,
        *,
        candidate_calls: int,
        b_model_calls: int,
        embedding_items: int,
        http_requests: int,
    ) -> None:
        if (
            candidate_calls > self.max_candidate_calls
            or b_model_calls > self.max_b_model_calls
            or embedding_items > self.max_embedding_items
            or http_requests > self.max_http_requests
        ):
            raise HardCallBudgetExceeded("BLOCKED_CALL_BUDGET")


@dataclass
class ProviderUsageLedger:
    budget: CallBudget
    rows: list[dict[str, Any]] = field(default_factory=list)
    candidate_calls: int = 0
    b_model_calls: int = 0
    embedding_items: int = 0
    http_requests: int = 0
    retry_count: int = 0

    def reserve(self, *, provider: str, embedding_items: int = 0) -> None:
        candidate_calls = self.candidate_calls + int(provider == "candidate-llm")
        b_model_calls = self.b_model_calls + int(provider == "b-model")
        total_items = self.embedding_items + embedding_items
        http_requests = self.http_requests + 1
        self.budget.validate(
            candidate_calls=candidate_calls,
            b_model_calls=b_model_calls,
            embedding_items=total_items,
            http_requests=http_requests,
        )
        self.candidate_calls = candidate_calls
        self.b_model_calls = b_model_calls
        self.embedding_items = total_items
        self.http_requests = http_requests

    def record(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        latency_ms: int,
        usage: dict[str, Any] | None,
        retry_count: int,
        embedding_items: int = 0,
        error_type: str | None = None,
    ) -> None:
        safe_usage = {
            key: value
            for key, value in (usage or {}).items()
            if key
            in {
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "input_tokens",
                "output_tokens",
                "credit",
                "credits",
            }
            and isinstance(value, (int, float))
        }
        self.retry_count += retry_count
        self.rows.append(
            {
                "provider": provider,
                "model": model,
                "operation": operation,
                "request_count": 1,
                "embedding_item_count": embedding_items,
                "latency_ms": latency_ms,
                "usage": safe_usage,
                "retry_count": retry_count,
                "error_type": error_type,
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_request_count": self.candidate_calls,
            "b_model_request_count": self.b_model_calls,
            "embedding_item_count": self.embedding_items,
            "http_request_count": self.http_requests,
            "retry_count": self.retry_count,
            "calls": list(self.rows),
        }


class MeteredChatClient:
    """Transparent counter around the production Candidate chat adapter."""

    def __init__(self, client, ledger: ProviderUsageLedger):
        self._client = client
        self._ledger = ledger
        self.settings = client.settings

    def complete(self, messages):
        self._ledger.reserve(provider="candidate-llm")
        started = time.monotonic()
        try:
            result = self._client.complete(messages)
        except Exception as exc:
            self._ledger.record(
                provider="candidate-llm",
                model=self.settings.model,
                operation="candidate-stage",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                usage=None,
                retry_count=0,
                error_type=type(exc).__name__,
            )
            raise
        self._ledger.record(
            provider="candidate-llm",
            model=self.settings.model,
            operation="candidate-stage",
            latency_ms=result.latency_ms,
            usage={
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
            },
            retry_count=0,
        )
        return result


class MeteredEmbeddingClient:
    """Transparent per-item counter around the production Embedding adapter."""

    def __init__(self, client, ledger: ProviderUsageLedger):
        self._client = client
        self._ledger = ledger
        self.settings = client.settings

    def embed(self, *, text: str, model: str, dimensions: int):
        self._ledger.reserve(provider="embedding", embedding_items=1)
        started = time.monotonic()
        try:
            result = self._client.embed_detailed(
                text=text,
                model=model,
                dimensions=dimensions,
            )
        except Exception as exc:
            self._ledger.record(
                provider="embedding",
                model=model,
                operation="embedding-item",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                usage=None,
                retry_count=0,
                embedding_items=1,
                error_type=type(exc).__name__,
            )
            raise
        self._ledger.record(
            provider="embedding",
            model=model,
            operation="embedding-item",
            latency_ms=result.latency_ms,
            usage=asdict(result.usage),
            retry_count=result.retry_count,
            embedding_items=1,
        )
        return result.vector


class MeteredBModelClient:
    """Transparent per-Node counter around the production B-model adapter."""

    def __init__(self, client, ledger: ProviderUsageLedger):
        self._client = client
        self._ledger = ledger
        self.settings = client.settings
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_model(self) -> str:
        return self._client.provider_model

    def recommend(self, *, source_node, retrieval_candidates):
        self._ledger.reserve(provider="b-model")
        started = time.monotonic()
        try:
            result = self._client.recommend_detailed(
                source_node=source_node,
                retrieval_candidates=retrieval_candidates,
            )
        except Exception as exc:
            self._ledger.record(
                provider="b-model",
                model=self.provider_model,
                operation="node-recommendation",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                usage=None,
                retry_count=0,
                error_type=type(exc).__name__,
            )
            raise
        self._ledger.record(
            provider="b-model",
            model=self.provider_model,
            operation="node-recommendation",
            latency_ms=result.latency_ms,
            usage=result.usage,
            retry_count=result.retry_count,
        )
        self.calls.append(
            {
                "sourceNode": redact(source_node),
                "retrievalCandidates": redact(retrieval_candidates),
                "decision": redact(result.decision),
            }
        )
        return result.decision


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): ("<redacted>" if _SECRET_FIELD.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


def contains_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (
                bool(_SECRET_FIELD.search(str(key)))
                and item != "<redacted>"
            )
            or contains_secret_field(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret_field(item) for item in value)
    return False


def synthetic_transcript_text() -> str:
    return "\n\n".join(
        f"[{row['startMs'] // 60000:02d}:{(row['startMs'] // 1000) % 60:02d}] "
        f"{row['speakerLabel']}:\n{row['text']}"
        for row in TRANSCRIPT_SEGMENTS
    )


def meeting_input() -> dict[str, Any]:
    return {
        "projectId": PROJECT_ID,
        "externalMeetingId": MEETING_ID,
        "requestId": "gms-fatal-smoke-request",
        "recordingHash": RECORDING_HASH,
        "segments": [dict(row) for row in TRANSCRIPT_SEGMENTS],
    }


def derive_database_urls(base_url: str, run_id: str) -> tuple[URL, URL, str]:
    db_name = "gms_smoke_" + re.sub(r"[^0-9A-Za-z_]", "_", run_id).lower()
    if not re.fullmatch(r"gms_smoke_[0-9a-z_]{6,80}", db_name):
        raise SmokeBlocked("unsafe disposable database name")
    parsed = make_url(base_url)
    if not parsed.drivername.startswith("postgresql"):
        raise SmokeBlocked("fatal smoke requires PostgreSQL")
    return parsed.set(database="postgres"), parsed.set(database=db_name), db_name


def create_disposable_database(admin_url: URL, db_name: str) -> None:
    if not db_name.startswith("gms_smoke_"):
        raise SmokeBlocked("unsafe database creation target")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar_one_or_none()
            if exists:
                raise SmokeBlocked("disposable database already exists")
            connection.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
    finally:
        engine.dispose()


def drop_disposable_database(admin_url: URL, db_name: str) -> None:
    if not re.fullmatch(r"gms_smoke_[0-9a-z_]{6,80}", db_name):
        raise SmokeBlocked("unsafe database cleanup target")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        engine.dispose()


def database_exists(admin_url: URL, db_name: str) -> bool:
    engine = create_engine(admin_url)
    try:
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": db_name},
                ).scalar_one_or_none()
            )
    finally:
        engine.dispose()


def upgrade_database(repo_root: Path, target_url: URL) -> None:
    config = Config(str(repo_root / "alembic.ini"))
    rendered = target_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(config, "head")


def _create_seed_node(
    session_factory,
    *,
    project_id: str,
    category: str,
    title: str,
    content: str,
    request_id: str,
) -> uuid.UUID:
    return create_user_node(
        session_factory,
        project_id=project_id,
        actor_id="gms-fatal-smoke-seed",
        request_id=request_id,
        node_type="DECISION",
        category=category,
        title=title,
        content=content,
        due_date=None,
        evidence_assertion=f"synthetic seed assertion: {title}",
        external_meeting_id=None,
    ).node_id


def seed_graph(session_factory) -> dict[str, uuid.UUID]:
    nodes = {
        "D_CORRECT": _create_seed_node(
            session_factory,
            project_id=PROJECT_ID,
            category="BACKEND",
            title="JWT 인증 방식 채택",
            content="로그인 인증은 JWT 방식을 사용한다.",
            request_id="seed-d-correct",
        ),
        "D_CONTRADICTORY": _create_seed_node(
            session_factory,
            project_id=PROJECT_ID,
            category="BACKEND",
            title="세션 인증 방식으로 전환",
            content="JWT를 폐기하고 세션 기반 인증으로 전환한다.",
            request_id="seed-d-contradictory",
        ),
        "D_FRONTEND": _create_seed_node(
            session_factory,
            project_id=PROJECT_ID,
            category="FRONTEND",
            title="로그인 실패 UX 개선",
            content="로그인 실패 화면과 사용자 안내를 개선한다.",
            request_id="seed-d-frontend",
        ),
        "D_OTHER_PROJECT": _create_seed_node(
            session_factory,
            project_id=OTHER_PROJECT_ID,
            category="BACKEND",
            title="JWT 인증 방식 채택",
            content="로그인 인증은 JWT 방식을 사용한다.",
            request_id="seed-d-other-project",
        ),
        "D_DELETED_TRAP": _create_seed_node(
            session_factory,
            project_id=PROJECT_ID,
            category="BACKEND",
            title="JWT 인증 방식 채택 삭제본",
            content="로그인 인증은 JWT 방식을 사용한다.",
            request_id="seed-d-deleted",
        ),
    }
    with session_factory() as session:
        trap = session.get(Node, nodes["D_DELETED_TRAP"])
        trap.graph_state = "DELETED"
        trap.deleted_at = datetime.now(timezone.utc)
        trap.deleted_by = "gms-fatal-smoke-seed"
        trap.version += 1
        session.commit()
    return nodes


def embed_seed_graph(
    session_factory,
    *,
    seed_nodes: dict[str, uuid.UUID],
    embedding_client: MeteredEmbeddingClient,
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
) -> None:
    with session_factory() as session:
        for node_id in seed_nodes.values():
            node = session.get(Node, node_id)
            embedding_input = load_current_revision_embedding_input(session, node=node)
            vector = embedding_client.embed(
                text=embedding_input.text,
                model=embedding_model,
                dimensions=embedding_dimension,
            )
            session.add(
                NodeEmbedding(
                    node_id=node.id,
                    embedding_version=embedding_version,
                    embedding_model=embedding_model,
                    dimension=embedding_dimension,
                    embedded_text_hash=embedding_input.text_hash,
                    embedding=validate_embedding(
                        vector,
                        expected_dimension=embedding_dimension,
                    ),
                    status="READY",
                    embedded_at=datetime.now(timezone.utc),
                )
            )
        session.commit()


def project_graph_version(session_factory, project_id: str = PROJECT_ID) -> int:
    with session_factory() as session:
        row = session.get(ProjectGraphState, project_id)
        return row.graph_version if row is not None else 0


def table_counts(session_factory) -> dict[str, int]:
    models = (
        Node,
        Relation,
        MergeOperation,
        Evidence,
        NodeRevisionEvidence,
        OutboxEvent,
        MeetingSummary,
    )
    with session_factory() as session:
        return {
            model.__tablename__: int(
                session.scalar(select(func.count()).select_from(model)) or 0
            )
            for model in models
        }


def candidate_snapshot(session_factory) -> dict[str, Any]:
    with session_factory() as session:
        request = session.execute(
            select(Request).where(
                Request.project_id == PROJECT_ID,
                Request.external_meeting_id == MEETING_ID,
            )
        ).scalar_one()
        rows = list(
            session.execute(
                select(NodeCandidate)
                .where(NodeCandidate.request_id == request.id)
                .order_by(NodeCandidate.source_item_id)
            ).scalars()
        )
        return {
            "requestId": str(request.id),
            "status": request.status,
            "rawExtraction": redact(request.raw_extraction),
            "rawJudgment": redact(request.raw_judgment),
            "candidates": [
                {
                    "id": str(row.id),
                    "sourceItemId": row.source_item_id,
                    "nodeType": row.suggested_node_type,
                    "category": row.suggested_category,
                    "title": row.suggested_title,
                    "content": row.suggested_content,
                    "parentCandidateId": (
                        str(row.suggested_parent_candidate_id)
                        if row.suggested_parent_candidate_id
                        else None
                    ),
                    "rawItem": redact(row.raw_item),
                }
                for row in rows
            ],
        }


def retrieval_snapshot(session_factory) -> list[dict[str, Any]]:
    with session_factory() as session:
        runs = list(
            session.execute(
                select(NodeAnalysisRun)
                .join(Node, Node.id == NodeAnalysisRun.source_node_id)
                .where(
                    Node.project_id == PROJECT_ID,
                    Node.source_meeting_id == MEETING_ID,
                )
                .order_by(NodeAnalysisRun.created_at, NodeAnalysisRun.id)
            ).scalars()
        )
        output = []
        for run in runs:
            results = list(
                session.execute(
                    select(RetrievalResult)
                    .where(RetrievalResult.analysis_run_id == run.id)
                    .order_by(RetrievalResult.rank, RetrievalResult.target_node_id)
                ).scalars()
            )
            output.append(
                {
                    "analysisRunId": str(run.id),
                    "sourceNodeId": str(run.source_node_id),
                    "status": run.status,
                    "results": [
                        {
                            "targetNodeId": str(row.target_node_id),
                            "targetNodeVersion": row.target_node_version,
                            "rank": row.rank,
                            "similarity": row.similarity,
                        }
                        for row in results
                    ],
                }
            )
        return output


def graph_snapshot(session_factory, seed_nodes: dict[str, uuid.UUID]) -> dict[str, Any]:
    with session_factory() as session:
        nodes = list(session.execute(select(Node).order_by(Node.project_id, Node.id)).scalars())
        relations = list(session.execute(select(Relation).order_by(Relation.id)).scalars())
        return {
            "seedNodeIds": {key: str(value) for key, value in seed_nodes.items()},
            "nodes": [
                {
                    "id": str(row.id),
                    "projectId": row.project_id,
                    "sourceCandidateId": str(row.source_candidate_id) if row.source_candidate_id else None,
                    "nodeType": row.node_type,
                    "category": row.category,
                    "title": row.title,
                    "content": row.content,
                    "graphState": row.graph_state,
                    "parentId": str(row.parent_id) if row.parent_id else None,
                    "mergedIntoNodeId": str(row.merged_into_node_id) if row.merged_into_node_id else None,
                    "version": row.version,
                    "deleted": row.deleted_at is not None,
                }
                for row in nodes
            ],
            "relations": [
                {
                    "id": str(row.id),
                    "projectId": row.project_id,
                    "fromNodeId": str(row.from_node_id),
                    "toNodeId": str(row.to_node_id),
                    "relationType": row.relation_type,
                    "status": row.status,
                }
                for row in relations
            ],
        }


def outbox_snapshot(session_factory) -> list[dict[str, Any]]:
    with session_factory() as session:
        rows = list(
            session.execute(
                select(OutboxEvent).order_by(OutboxEvent.created_at, OutboxEvent.id)
            ).scalars()
        )
        return [
            {
                "id": str(row.id),
                "eventType": row.event_type,
                "aggregateType": row.aggregate_type,
                "aggregateId": row.aggregate_id,
                "projectId": row.project_id,
                "schemaVersion": row.schema_version,
                "payload": redact(row.payload),
                "status": row.status,
            }
            for row in rows
        ]


def _classify_candidate(candidate: NodeCandidate) -> str:
    title = candidate.suggested_title.lower()
    content = candidate.suggested_content.lower()
    combined = title + " " + content
    if candidate.suggested_node_type == "DECISION":
        return "C1"
    if candidate.suggested_node_type == "ACTION":
        return "C2"
    if candidate.suggested_category == "BACKEND" and (
        "token" in combined or "토큰" in combined or "회전" in combined
    ):
        return "C3"
    if candidate.suggested_category == "FRONTEND":
        return "C4"
    return candidate.source_item_id


def evaluate_invariants(
    session_factory,
    *,
    seed_nodes: dict[str, uuid.UUID],
    graph_version_before: int,
    graph_version_after: int,
    counts_before_replay: dict[str, int],
    counts_after_replay: dict[str, int],
    provider_calls_before_replay: int,
    provider_calls_after_replay: int,
) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    assertions: list[dict[str, Any]] = []
    warnings: list[str] = []
    outcomes: dict[str, str] = {}

    def check(name: str, passed: bool, detail: str) -> None:
        assertions.append({"name": name, "passed": bool(passed), "detail": detail})

    check(
        "graph_version_exactly_once",
        graph_version_after == graph_version_before + 1,
        f"before={graph_version_before}, after={graph_version_after}",
    )
    check(
        "duplicate_replay_no_db_side_effect",
        counts_before_replay == counts_after_replay,
        f"before={counts_before_replay}, after={counts_after_replay}",
    )
    check(
        "duplicate_replay_no_provider_call",
        provider_calls_before_replay == provider_calls_after_replay,
        f"before={provider_calls_before_replay}, after={provider_calls_after_replay}",
    )

    with session_factory() as session:
        request = session.execute(
            select(Request).where(
                Request.project_id == PROJECT_ID,
                Request.external_meeting_id == MEETING_ID,
            )
        ).scalar_one()
        candidates = list(
            session.execute(
                select(NodeCandidate).where(NodeCandidate.request_id == request.id)
            ).scalars()
        )
        check("candidate_count_3_or_4", len(candidates) in {3, 4}, f"count={len(candidates)}")
        if len(candidates) == 3:
            warnings.append("LOW_IMPORTANCE_ISSUE_OMITTED")

        candidate_ids = [row.id for row in candidates]
        generated_nodes = list(
            session.execute(select(Node).where(Node.source_candidate_id.in_(candidate_ids))).scalars()
        )
        by_candidate = {row.source_candidate_id: row for row in generated_nodes}
        check(
            "one_graph_node_per_candidate",
            len(by_candidate) == len(candidates),
            f"candidates={len(candidates)}, nodes={len(by_candidate)}",
        )
        all_nodes = {row.id: row for row in session.execute(select(Node)).scalars()}

        segment_rows = {
            row.segment_id: row
            for row in session.execute(
                select(TranscriptSegment).where(
                    TranscriptSegment.project_id == PROJECT_ID,
                    TranscriptSegment.external_meeting_id == MEETING_ID,
                )
            ).scalars()
        }
        evidence_ok = True
        for node in generated_nodes:
            links = list(
                session.execute(
                    select(NodeRevisionEvidence).where(
                        NodeRevisionEvidence.node_revision_id == node.current_revision_id
                    )
                ).scalars()
            )
            transcript_count = 0
            for link in links:
                proof = session.get(Evidence, link.evidence_id)
                if proof is None or proof.source_type != "TRANSCRIPT":
                    continue
                transcript_count += 1
                segment = segment_rows.get(proof.source_segment_id)
                if (
                    proof.project_id != PROJECT_ID
                    or proof.external_meeting_id != MEETING_ID
                    or segment is None
                    or proof.quoted_text not in (segment.normalized_text or segment.text)
                ):
                    evidence_ok = False
            if transcript_count == 0:
                evidence_ok = False
        check("evidence_grounded", evidence_ok, "generated current Revisions use exact meeting transcript spans")

        active_relations = list(
            session.execute(
                select(Relation).where(
                    Relation.status == "CONFIRMED",
                    Relation.valid_to.is_(None),
                )
            ).scalars()
        )
        relation_boundary_ok = True
        parent_ok = True
        self_edge = False
        for relation in active_relations:
            source = all_nodes[relation.from_node_id]
            target = all_nodes[relation.to_node_id]
            if source.project_id != relation.project_id or target.project_id != relation.project_id:
                relation_boundary_ok = False
            if relation.from_node_id == relation.to_node_id:
                self_edge = True
            if relation.relation_type == "ATTACHED_TO":
                allowed = (
                    {"DECISION"}
                    if source.node_type == "ACTION"
                    else {"DECISION", "ACTION"}
                    if source.node_type == "ISSUE"
                    else set()
                )
                if (
                    target.node_type not in allowed
                    or target.category != source.category
                    or target.graph_state != "ACTIVE"
                ):
                    parent_ok = False
        check("cross_project_relation_absent", relation_boundary_ok, "confirmed Relation endpoints remain project-scoped")
        check("parent_type_category_state_valid", parent_ok, "ATTACHED_TO parent type/category/state is valid")
        check("self_link_absent", not self_edge, "no Relation points to itself")

        bad_merge = False
        contradictory_merge = False
        for node in generated_nodes:
            if node.merged_into_node_id is None:
                continue
            target = all_nodes[node.merged_into_node_id]
            if node.merged_into_node_id == seed_nodes["D_CONTRADICTORY"]:
                contradictory_merge = True
            if (
                target.project_id != node.project_id
                or target.category != node.category
                or target.node_type != node.node_type
                or target.graph_state != "ACTIVE"
            ):
                bad_merge = True
        check("contradictory_merge_absent", not contradictory_merge, "JWT retention did not merge into session conversion")
        check("merge_boundary_valid", not bad_merge, "applied MERGE stays in project/category/type and targets ACTIVE")

        cycle = False
        for node in generated_nodes:
            seen: set[uuid.UUID] = set()
            current = node
            while current.parent_id is not None:
                if current.id in seen:
                    cycle = True
                    break
                seen.add(current.id)
                current = all_nodes[current.parent_id]
        check("parent_cycle_absent", not cycle, "generated parent chains are acyclic")

        retrieval_target_ids = {
            row.target_node_id
            for row in session.execute(
                select(RetrievalResult)
                .join(NodeAnalysisRun, NodeAnalysisRun.id == RetrievalResult.analysis_run_id)
                .join(Node, Node.id == NodeAnalysisRun.source_node_id)
                .where(
                    Node.project_id == PROJECT_ID,
                    Node.source_meeting_id == MEETING_ID,
                )
            ).scalars()
        }
        excluded = {
            seed_nodes["D_OTHER_PROJECT"],
            seed_nodes["D_DELETED_TRAP"],
        }
        check("deleted_and_other_project_retrieval_excluded", not bool(retrieval_target_ids & excluded), "trap targets absent from durable RetrievalResult")

        delivery = session.execute(
            select(AnalysisDeliveryState).where(
                AnalysisDeliveryState.project_id == PROJECT_ID,
                AnalysisDeliveryState.external_meeting_id == MEETING_ID,
            )
        ).scalar_one()
        barrier_ok = (
            delivery.status == "SUCCEEDED"
            and delivery.required_graph_version == graph_version_after
            and delivery.required_summary_version == 1
        )
        check("completion_barrier", barrier_ok, f"status={delivery.status}, graph={delivery.required_graph_version}, summary={delivery.required_summary_version}")

        run = session.execute(
            select(GenerationRun).where(
                GenerationRun.project_id == PROJECT_ID,
                GenerationRun.external_meeting_id == MEETING_ID,
            )
        ).scalar_one()
        completion_events = list(
            session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED",
                    OutboxEvent.aggregate_id == str(run.id),
                )
            ).scalars()
        )
        check("single_graph_completion_outbox", len(completion_events) == 1, f"count={len(completion_events)}")
        check("request_and_generation_completed", request.status == "COMPLETED" and run.status in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, f"request={request.status}, run={run.status}")

        for candidate in candidates:
            key = _classify_candidate(candidate)
            node = by_candidate.get(candidate.id)
            if node is None:
                outcomes[key] = "MISSING_GRAPH_NODE"
                continue
            target = all_nodes[node.merged_into_node_id] if node.merged_into_node_id else node
            outcomes[key] = (
                f"{node.graph_state} -> {target.title} "
                f"({target.node_type}/{target.category})"
            )
            if node.node_type in {"ACTION", "ISSUE"} and node.graph_state == "UNATTACHED":
                warnings.append(f"{key}_UNATTACHED")

    return assertions, sorted(set(warnings)), outcomes


def run_git_snapshot(repo_root: Path) -> str:
    commands = (
        ["git", "branch", "--show-current"],
        ["git", "rev-parse", "HEAD"],
        ["git", "status", "--short"],
        ["git", "log", "--oneline", "-5"],
    )
    blocks: list[str] = []
    for args in commands:
        result = subprocess.run(
            args,
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        blocks.append(f"$ {' '.join(args)}\n{(result.stdout or '').strip()}\n")
    return "\n".join(blocks)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(redact(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ensure_required_artifacts(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "seed-graph.json",
        "candidate-output-redacted.json",
        "retrieval-results.json",
        "b-model-output-redacted.json",
        "final-graph.json",
        "outbox-events.json",
        "provider-usage.json",
        "fatal-assertions.json",
    ):
        path = output_dir / name
        if not path.exists():
            write_json(path, {})
    for name in (
        "preflight-budget.md",
        "quality-warnings.md",
        "db-integrity-report.md",
        "idempotency-report.md",
        "cleanup-report.md",
        "final-report.md",
    ):
        path = output_dir / name
        if not path.exists():
            path.write_text("Not completed.\n", encoding="utf-8")
    for name in (
        "synthetic-transcript.txt",
        "test-log.txt",
        "git-before.txt",
        "git-after.txt",
    ):
        path = output_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")


__all__ = [
    "CallBudget",
    "FatalSmokeFailure",
    "HardCallBudgetExceeded",
    "MEETING_ID",
    "MeteredBModelClient",
    "MeteredChatClient",
    "MeteredEmbeddingClient",
    "OTHER_PROJECT_ID",
    "PIPELINE_VERSION",
    "PROJECT_ID",
    "ProviderUsageLedger",
    "RECORDING_HASH",
    "SmokeBlocked",
    "TRANSCRIPT_SEGMENTS",
    "candidate_snapshot",
    "contains_secret_field",
    "create_disposable_database",
    "database_exists",
    "derive_database_urls",
    "drop_disposable_database",
    "embed_seed_graph",
    "ensure_required_artifacts",
    "evaluate_invariants",
    "graph_snapshot",
    "meeting_input",
    "outbox_snapshot",
    "project_graph_version",
    "redact",
    "retrieval_snapshot",
    "run_git_snapshot",
    "seed_graph",
    "synthetic_transcript_text",
    "table_counts",
    "upgrade_database",
    "write_json",
]
