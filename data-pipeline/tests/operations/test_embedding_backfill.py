from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from data_pipeline.config import RetrievalSettings
from data_pipeline.pipeline.analysis import _embedding_text_for_analysis
from data_pipeline.pipeline.automatic_graph import CandidateSnapshot, _embedding_text
from data_pipeline.pipeline.revisions import (
    EvidenceSpec,
    create_node_revision,
    current_revision_evidence_specs,
)
from data_pipeline.retrieval import (
    build_embedding_text_from_parts,
    embedding_text_hash,
    load_current_revision_embedding_input,
)
from data_pipeline.operations.embedding_backfill import (
    BackfillOptions,
    BackfillReason,
    _classify_embedding,
    run_embedding_backfill,
    write_backfill_report,
)
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.storage import (
    Node,
    NodeEmbedding,
    NodeEvidence,
    NodeRevisionEvidence,
)

PROJECT = "embedding-backfill-project"
OTHER_PROJECT = "embedding-backfill-other"
DIMENSION = 1536
SETTINGS = RetrievalSettings(
    embedding_model="text-embedding-3-small",
    embedding_version=EMBEDDING_CONTRACT_VERSION,
    embedding_dim=DIMENSION,
)


def _evidence(
    segment_id: str = "segment-1",
    quote: str = "현재 Revision의 근거 문장",
) -> EvidenceSpec:
    return EvidenceSpec(
        external_meeting_id=None,
        transcript_segment_id=None,
        source_segment_id=segment_id,
        speaker_label=None,
        start_ms=None,
        end_ms=None,
        quote_start=None,
        quote_end=None,
        quoted_text=quote,
        source_type="LEGACY",
        support_type="LEGACY",
        legacy_imported=True,
    )


def _seed_node(
    session_factory,
    *,
    project_id: str = PROJECT,
    node_id: uuid.UUID | None = None,
    state: str = "ACTIVE",
    title: str = "Embedding 대상",
    content: str = "현재 Revision 본문",
    evidence_specs: list[EvidenceSpec] | None = None,
    with_revision: bool = True,
    merged_into_node_id: uuid.UUID | None = None,
) -> uuid.UUID:
    session = session_factory()
    try:
        node = Node(
            id=node_id or uuid.uuid4(),
            project_id=project_id,
            source_meeting_id=f"meeting-{uuid.uuid4()}",
            source_item_id=f"item-{uuid.uuid4()}",
            node_type="DECISION",
            category="INFRA",
            title=title,
            content=content,
            graph_state=state,
            merged_into_node_id=merged_into_node_id,
            analysis_status="PENDING",
            version=1,
            deleted_at=(
                datetime.now(timezone.utc) if state == "DELETED" else None
            ),
        )
        session.add(node)
        session.flush()
        if with_revision:
            create_node_revision(
                session,
                node=node,
                title=title,
                content=content,
                node_type="DECISION",
                category="INFRA",
                due_date=None,
                created_by_type="LEGACY",
                created_by_id=None,
                generation_run_id=None,
                evidence_specs=(
                    evidence_specs if evidence_specs is not None else [_evidence()]
                ),
                requires_evidence=bool(
                    evidence_specs if evidence_specs is not None else [_evidence()]
                ),
                legacy_imported=True,
            )
        session.commit()
        return node.id
    finally:
        session.close()


def _current_input(session_factory, node_id: uuid.UUID):
    with session_factory() as session:
        node = session.get(Node, node_id)
        return load_current_revision_embedding_input(session, node=node)


def _put_embedding(
    session_factory,
    node_id: uuid.UUID,
    *,
    status: str = "READY",
    text_hash: str | None = None,
    model: str = SETTINGS.embedding_model,
    dimension: int = SETTINGS.embedding_dim,
    vector: list[float] | None = None,
) -> None:
    with session_factory() as session:
        row = NodeEmbedding(
            node_id=node_id,
            embedding_version=SETTINGS.embedding_version,
            embedding_model=model,
            dimension=dimension,
            embedded_text_hash=text_hash,
            embedding=(
                vector
                if vector is not None
                else [1.0, *([0.0] * (DIMENSION - 1))]
            ),
            status=status,
        )
        session.add(row)
        session.commit()


class _FakeEmbedding:
    def __init__(self, callback=None, failures: int = 0):
        self.callback = callback
        self.failures = failures
        self.calls = 0
        self.texts: list[str] = []

    def embed(self, *, text: str, model: str, dimensions: int):
        assert model == SETTINGS.embedding_model
        self.calls += 1
        self.texts.append(text)
        if self.callback is not None:
            self.callback(text)
        if self.calls <= self.failures:
            raise RuntimeError("fake provider failure")
        return [1.0, *([0.0] * (dimensions - 1))]


def _run(
    session_factory,
    *,
    apply: bool,
    client: _FakeEmbedding | None = None,
    **option_overrides,
):
    options = BackfillOptions(
        project_id=option_overrides.pop("project_id", PROJECT),
        apply=apply,
        **option_overrides,
    )
    return run_embedding_backfill(
        session_factory,
        options=options,
        embedding_client_factory=((lambda: client) if client is not None else None),
        settings=SETTINGS,
        run_id="test-run",
    )


def test_canonical_serializer_matches_automatic_snapshot_and_current_revision(
    session_factory,
) -> None:
    specs = [_evidence("segment-2", "두 번째"), _evidence("segment-1", "첫 번째")]
    node_id = _seed_node(
        session_factory,
        node_id=uuid.uuid4(),
        title="동일 제목",
        content="동일 본문",
        evidence_specs=specs,
    )
    snapshot = CandidateSnapshot(
        candidate_id=uuid.uuid4(),
        source_item_id="item-1",
        project_id=PROJECT,
        external_meeting_id="meeting-1",
        node_id=node_id,
        node_type="DECISION",
        category="INFRA",
        title="동일 제목",
        content="동일 본문",
        due_date=None,
        suggested_parent_candidate_id=None,
        evidence=tuple(reversed(specs)),
    )
    current = _current_input(session_factory, node_id)

    assert _embedding_text(snapshot) == current.text
    assert embedding_text_hash(_embedding_text(snapshot)) == current.text_hash


def test_evidence_order_is_stable_and_analysis_uses_current_revision(
    session_factory,
) -> None:
    first = build_embedding_text_from_parts(
        node_type="DECISION",
        category="INFRA",
        title="제목",
        content="본문",
        evidence_pairs=[("b", "둘"), ("a", "하나")],
    )
    second = build_embedding_text_from_parts(
        node_type="DECISION",
        category="INFRA",
        title="제목",
        content="본문",
        evidence_pairs=[("a", "하나"), ("b", "둘")],
    )
    assert first == second

    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        current = load_current_revision_embedding_input(session, node=node)
        session.execute(delete(NodeEvidence).where(NodeEvidence.node_id == node_id))
        node.title = "current Revision과 다른 projection 제목"
        node.content = "current Revision과 다른 projection 본문"
        session.flush()
        assert _embedding_text_for_analysis(session, node=node) == current.text


def test_current_revision_does_not_depend_on_legacy_node_evidence(
    session_factory,
) -> None:
    node_id = _seed_node(session_factory)
    expected = _current_input(session_factory, node_id)
    with session_factory() as session:
        session.execute(delete(NodeEvidence).where(NodeEvidence.node_id == node_id))
        session.commit()

    assert _current_input(session_factory, node_id) == expected


def test_dry_run_filters_project_state_merge_and_node_id(
    session_factory,
) -> None:
    active = _seed_node(session_factory, state="ACTIVE")
    unattached = _seed_node(session_factory, state="UNATTACHED")
    target = _seed_node(session_factory, state="ACTIVE")
    _seed_node(
        session_factory,
        state="MERGED",
        merged_into_node_id=target,
    )
    for state in ("EXCLUDED", "ARCHIVED", "DELETED"):
        _seed_node(session_factory, state=state)
    other = _seed_node(session_factory, project_id=OTHER_PROJECT)

    report = _run(session_factory, apply=False)

    assert {result.node_id for result in report.results} == {active, unattached, target}
    assert report.counts()["wouldGenerate"] == 3
    assert _run(
        session_factory,
        apply=False,
        project_id=PROJECT,
        node_id=other,
    ).results == []


def test_reusable_ready_skips_provider_and_is_idempotent(session_factory) -> None:
    node_id = _seed_node(session_factory)
    current = _current_input(session_factory, node_id)
    _put_embedding(session_factory, node_id, text_hash=current.text_hash)
    client = _FakeEmbedding()

    first = _run(session_factory, apply=True, client=client)
    second = _run(session_factory, apply=True, client=client)

    assert [result.reason for result in first.results] == [
        BackfillReason.READY_REUSABLE
    ]
    assert second.counts()["reusable"] == 1
    assert client.calls == 0


@pytest.mark.parametrize(
    ("status", "expected_reason"),
    [
        (None, BackfillReason.MISSING),
        ("STALE", BackfillReason.STATUS_STALE),
        ("FAILED", BackfillReason.STATUS_FAILED),
        ("PENDING", BackfillReason.STATUS_PENDING),
    ],
)
def test_missing_and_non_ready_rows_are_regenerated(
    session_factory,
    status,
    expected_reason,
) -> None:
    node_id = _seed_node(session_factory)
    if status is not None:
        _put_embedding(
            session_factory,
            node_id,
            status=status,
            text_hash="0" * 64,
        )
    client = _FakeEmbedding()

    report = _run(session_factory, apply=True, client=client)

    assert report.results[0].reason is expected_reason
    assert report.results[0].status == "GENERATED"
    assert client.calls == 1
    with session_factory() as session:
        row = session.get(NodeEmbedding, (node_id, SETTINGS.embedding_version))
        assert row.status == "READY"
        assert row.embedded_text_hash == _current_input(
            session_factory,
            node_id,
        ).text_hash


def test_ready_hash_mismatch_is_staled_before_provider_failure(
    session_factory,
) -> None:
    node_id = _seed_node(session_factory)
    _put_embedding(session_factory, node_id, text_hash="f" * 64)
    client = _FakeEmbedding(failures=1)

    report = _run(session_factory, apply=True, client=client)

    assert report.results[0].reason is BackfillReason.EMBEDDING_PROVIDER_FAILED
    assert report.marked_stale == 1
    with session_factory() as session:
        assert session.get(
            NodeEmbedding,
            (node_id, SETTINGS.embedding_version),
        ).status == "STALE"


@pytest.mark.parametrize(
    "mutation",
    ["HASH", "MODEL", "VECTOR_MISSING", "VECTOR_INVALID"],
)
def test_invalid_ready_rows_are_staled_and_regenerated(
    session_factory,
    mutation,
) -> None:
    node_id = _seed_node(session_factory)
    current = _current_input(session_factory, node_id)
    _put_embedding(session_factory, node_id, text_hash=current.text_hash)
    with session_factory() as session:
        row = session.get(NodeEmbedding, (node_id, SETTINGS.embedding_version))
        if mutation == "HASH":
            row.embedded_text_hash = "0" * 64
        elif mutation == "MODEL":
            row.embedding_model = "old-model"
        elif mutation == "VECTOR_MISSING":
            row.embedding = None
        else:
            row.embedding = [0.0] * DIMENSION
        session.commit()
    client = _FakeEmbedding()

    report = _run(session_factory, apply=True, client=client)

    assert report.counts()["generated"] == 1
    assert report.marked_stale == 1
    assert client.calls == 1
    with session_factory() as session:
        row = session.get(NodeEmbedding, (node_id, SETTINGS.embedding_version))
        assert row.status == "READY"
        assert row.embedding_model == SETTINGS.embedding_model
        assert row.embedded_text_hash == current.text_hash


def test_dry_run_never_marks_invalid_ready_stale_or_builds_client(
    session_factory,
) -> None:
    node_id = _seed_node(session_factory)
    _put_embedding(session_factory, node_id, text_hash="f" * 64)
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        return _FakeEmbedding()

    report = run_embedding_backfill(
        session_factory,
        options=BackfillOptions(project_id=PROJECT),
        embedding_client_factory=factory,
        settings=SETTINGS,
    )

    assert report.results[0].status == "WOULD_GENERATE"
    assert report.results[0].reason is BackfillReason.TEXT_HASH_MISMATCH
    assert factory_calls == 0
    with session_factory() as session:
        assert session.get(
            NodeEmbedding,
            (node_id, SETTINGS.embedding_version),
        ).status == "READY"


def test_node_change_during_provider_call_discards_vector(session_factory) -> None:
    node_id = _seed_node(session_factory)

    def change_node(_text: str) -> None:
        with session_factory() as session:
            node = session.execute(
                select(Node).where(Node.id == node_id).with_for_update()
            ).scalar_one()
            create_node_revision(
                session,
                node=node,
                title=node.title,
                content="외부 호출 중 변경된 본문",
                node_type=node.node_type,
                category=node.category,
                due_date=node.due_date,
                created_by_type="USER",
                created_by_id="test",
                generation_run_id=None,
                evidence_specs=current_revision_evidence_specs(session, node=node),
            )
            session.commit()

    report = _run(
        session_factory,
        apply=True,
        client=_FakeEmbedding(callback=change_node),
    )

    assert report.results[0].reason is BackfillReason.NODE_CHANGED_DURING_EMBED
    with session_factory() as session:
        assert session.get(
            NodeEmbedding,
            (node_id, SETTINGS.embedding_version),
        ) is None
        assert session.get(Node, node_id).content == "외부 호출 중 변경된 본문"


def test_concurrent_ready_is_reused_without_overwrite(session_factory) -> None:
    node_id = _seed_node(session_factory)
    concurrent_vector = [0.0, 1.0, *([0.0] * (DIMENSION - 2))]

    def insert_ready(text: str) -> None:
        _put_embedding(
            session_factory,
            node_id,
            text_hash=embedding_text_hash(text),
            vector=concurrent_vector,
        )

    report = _run(
        session_factory,
        apply=True,
        client=_FakeEmbedding(callback=insert_ready),
    )

    assert report.results[0].reason is BackfillReason.CONCURRENT_READY_REUSED
    with session_factory() as session:
        assert list(
            session.get(
                NodeEmbedding,
                (node_id, SETTINGS.embedding_version),
            ).embedding
        ) == concurrent_vector


def test_max_calls_cursor_and_failure_isolation(session_factory) -> None:
    node_ids = [
        _seed_node(
            session_factory,
            node_id=uuid.UUID(int=index),
        )
        for index in range(1, 6)
    ]
    client = _FakeEmbedding(failures=1)

    report = _run(
        session_factory,
        apply=True,
        client=client,
        max_calls=2,
        batch_size=2,
    )

    assert client.calls == 2
    assert report.failed is True
    assert report.counts()["failed"] == 1
    assert report.counts()["generated"] == 1
    assert report.counts()["deferred"] == 3
    resumed = _run(
        session_factory,
        apply=False,
        after_node_id=node_ids[1],
    )
    assert [result.node_id for result in resumed.results] == node_ids[2:]


def test_missing_current_revision_is_skipped(session_factory) -> None:
    node_id = _seed_node(session_factory, with_revision=False)
    client = _FakeEmbedding()

    report = _run(session_factory, apply=True, client=client)

    assert report.results[0].status == "SKIPPED"
    assert report.results[0].reason is BackfillReason.NO_CURRENT_REVISION
    assert client.calls == 0


def test_damaged_required_revision_evidence_is_skipped(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        if session.get_bind().dialect.name == "postgresql":
            pytest.skip(
                "PostgreSQL trigger prevents creating this corruption fixture"
            )
        revision_id = session.get(Node, node_id).current_revision_id
        session.execute(
            delete(NodeRevisionEvidence).where(
                NodeRevisionEvidence.node_revision_id == revision_id
            )
        )
        session.commit()

    report = _run(
        session_factory,
        apply=True,
        client=_FakeEmbedding(),
    )

    assert report.results[0].reason is BackfillReason.INVALID_CURRENT_REVISION
    assert report.results[0].status == "SKIPPED"


def test_legacy_revision_without_evidence_is_allowed(session_factory) -> None:
    node_id = _seed_node(
        session_factory,
        evidence_specs=[],
    )

    report = _run(session_factory, apply=False)

    assert report.results[0].status == "WOULD_GENERATE"
    assert _current_input(session_factory, node_id).text.endswith(",[]]")


def test_classification_covers_ready_mismatch_and_invalid_vector() -> None:
    base = {
        "node_id": uuid.uuid4(),
        "embedding_version": SETTINGS.embedding_version,
        "embedding_model": SETTINGS.embedding_model,
        "dimension": DIMENSION,
        "embedded_text_hash": "a" * 64,
        "status": "READY",
    }
    assert _classify_embedding(
        NodeEmbedding(**base, embedding=None),
        text_hash="a" * 64,
        settings=SETTINGS,
    ) is BackfillReason.VECTOR_MISSING
    assert _classify_embedding(
        NodeEmbedding(**{**base, "embedding_model": "other"}, embedding=[1.0]),
        text_hash="a" * 64,
        settings=SETTINGS,
    ) is BackfillReason.MODEL_MISMATCH
    assert _classify_embedding(
        NodeEmbedding(**{**base, "dimension": 1}, embedding=[1.0]),
        text_hash="a" * 64,
        settings=SETTINGS,
    ) is BackfillReason.DIMENSION_MISMATCH
    assert _classify_embedding(
        NodeEmbedding(**base, embedding=[0.0] * DIMENSION),
        text_hash="a" * 64,
        settings=SETTINGS,
    ) is BackfillReason.VECTOR_INVALID


def test_report_is_secret_and_content_safe(session_factory, tmp_path: Path) -> None:
    _seed_node(
        session_factory,
        title="DO-NOT-LEAK-TITLE",
        content="DO-NOT-LEAK-CONTENT",
        evidence_specs=[_evidence("secret-segment", "DO-NOT-LEAK-EVIDENCE")],
    )
    report = _run(session_factory, apply=False)

    json_path, summary_path = write_backfill_report(
        report,
        report_directory=tmp_path,
    )
    rendered = json_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)

    assert payload["mode"] == "DRY_RUN"
    assert payload["counts"]["wouldGenerate"] == 1
    assert "DO-NOT-LEAK" not in rendered
    assert "embedding" not in payload["results"][0]
    assert summary_path.exists()


def test_option_and_storage_dimension_preflight() -> None:
    with pytest.raises(ValueError, match="states"):
        BackfillOptions(project_id=PROJECT, states=("MERGED",))
    with pytest.raises(ValueError, match="max_calls"):
        BackfillOptions(project_id=PROJECT, max_calls=0)
    with pytest.raises(ValueError, match="batch_size"):
        BackfillOptions(project_id=PROJECT, batch_size=0)
