"""Immutable Node revision and evidence application services."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from data_pipeline.storage import (
    Evidence,
    Node,
    NodeCandidate,
    NodeEmbedding,
    NodeRevision,
    NodeRevisionEvidence,
    TranscriptSegment,
    upsert_node_evidence,
)

from .errors import EvidenceValidationError, GraphMutationValidationError


@dataclass(frozen=True)
class EvidenceSpec:
    external_meeting_id: str | None
    transcript_segment_id: uuid.UUID | None
    source_segment_id: str | None
    speaker_label: str | None
    start_ms: int | None
    end_ms: int | None
    quote_start: int | None
    quote_end: int | None
    quoted_text: str
    source_type: str
    normalization_version: str | None = None
    support_type: str = "SUPPORTING"
    legacy_imported: bool = False


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_hash(project_id: str, spec: EvidenceSpec) -> str:
    return _canonical_hash(
        {
            "version": "revision-evidence-v1",
            "projectId": project_id,
            "meetingId": spec.external_meeting_id,
            "transcriptSegmentId": (
                str(spec.transcript_segment_id)
                if spec.transcript_segment_id is not None
                else None
            ),
            "sourceSegmentId": spec.source_segment_id,
            "speakerLabel": spec.speaker_label,
            "startMs": spec.start_ms,
            "endMs": spec.end_ms,
            "quoteStart": spec.quote_start,
            "quoteEnd": spec.quote_end,
            "quotedText": spec.quoted_text,
            "sourceType": spec.source_type,
            "normalizationVersion": spec.normalization_version,
        }
    )


def _normalization_version(segment: TranscriptSegment) -> str | None:
    metadata = segment.normalization_metadata or {}
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("dictionary_version") or metadata.get("version")
    return str(value) if value else None


def validated_candidate_evidence(
    session,
    *,
    candidate: NodeCandidate,
) -> tuple[list[EvidenceSpec], list[dict]]:
    """Resolve LLM spans against server-owned normalized transcript text.

    The model's quote is only a verification hint. Persisted ``quoted_text`` is
    always sliced by the server from ``TranscriptSegment.normalized_text``.
    """

    specs: list[EvidenceSpec] = []
    warnings: list[dict] = []
    for row in candidate.evidence:
        meeting_id = row.source_meeting_id or candidate.external_meeting_id
        segment = session.execute(
            select(TranscriptSegment).where(
                TranscriptSegment.project_id == candidate.project_id,
                TranscriptSegment.external_meeting_id == meeting_id,
                TranscriptSegment.segment_id == row.segment_id,
            )
        ).scalar_one_or_none()
        text = (
            (segment.normalized_text or segment.text)
            if segment is not None
            else None
        )
        valid = (
            segment is not None
            and isinstance(row.quote_start, int)
            and isinstance(row.quote_end, int)
            and 0 <= row.quote_start < row.quote_end <= len(text)
            and text[row.quote_start:row.quote_end] == row.quote
        )
        if not valid:
            warnings.append(
                {
                    "code": "INVALID_EVIDENCE_SPAN",
                    "candidateId": str(candidate.id),
                    "segmentId": row.segment_id,
                }
            )
            continue
        assert segment is not None and text is not None
        specs.append(
            EvidenceSpec(
                external_meeting_id=meeting_id,
                transcript_segment_id=segment.id,
                source_segment_id=segment.segment_id,
                speaker_label=segment.speaker_label,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                quote_start=row.quote_start,
                quote_end=row.quote_end,
                quoted_text=text[row.quote_start:row.quote_end],
                source_type="TRANSCRIPT",
                normalization_version=_normalization_version(segment),
                support_type=(
                    "PRIMARY" if not specs else "SUPPORTING"
                ),
            )
        )
    return specs, warnings


def user_assertion_evidence(text: str) -> EvidenceSpec:
    assertion = text.strip()
    if not assertion:
        raise EvidenceValidationError("user assertion evidence must not be blank")
    return EvidenceSpec(
        external_meeting_id=None,
        transcript_segment_id=None,
        source_segment_id=None,
        speaker_label=None,
        start_ms=None,
        end_ms=None,
        quote_start=None,
        quote_end=None,
        quoted_text=assertion,
        source_type="USER_ASSERTION",
        support_type="USER_ASSERTION",
    )


def _get_or_create_evidence(session, *, project_id: str, spec: EvidenceSpec) -> Evidence:
    immutable_hash = evidence_hash(project_id, spec)
    existing = session.execute(
        select(Evidence).where(
            Evidence.project_id == project_id,
            Evidence.immutable_hash == immutable_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Evidence(
        project_id=project_id,
        external_meeting_id=spec.external_meeting_id,
        transcript_segment_id=spec.transcript_segment_id,
        source_segment_id=spec.source_segment_id,
        speaker_label=spec.speaker_label,
        start_ms=spec.start_ms,
        end_ms=spec.end_ms,
        quote_start=spec.quote_start,
        quote_end=spec.quote_end,
        quoted_text=spec.quoted_text,
        source_type=spec.source_type,
        immutable_hash=immutable_hash,
        normalization_version=spec.normalization_version,
        legacy_imported=spec.legacy_imported,
    )
    session.add(row)
    session.flush()
    return row


def create_node_revision(
    session,
    *,
    node: Node,
    title: str,
    content: str,
    node_type: str,
    category: str,
    due_date: str | None,
    created_by_type: str,
    created_by_id: str | None,
    generation_run_id: uuid.UUID | None,
    evidence_specs: list[EvidenceSpec],
    requires_evidence: bool = True,
    legacy_imported: bool = False,
) -> NodeRevision:
    """Append an immutable revision and update the Node projection atomically."""

    title = title.strip()
    if not title:
        raise GraphMutationValidationError("node title must not be blank")
    if requires_evidence and not evidence_specs:
        raise EvidenceValidationError(
            "automatic Node revisions require at least one valid Evidence"
        )
    next_version = node.version
    if node.current_revision_id is not None:
        next_version += 1
    revision = NodeRevision(
        project_id=node.project_id,
        node_id=node.id,
        version=next_version,
        title=title,
        content=content,
        node_type=node_type,
        category=category,
        due_date=due_date,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        generation_run_id=generation_run_id,
        requires_evidence=requires_evidence,
        legacy_imported=legacy_imported,
    )
    session.add(revision)
    session.flush()

    for spec in evidence_specs:
        evidence = _get_or_create_evidence(
            session,
            project_id=node.project_id,
            spec=spec,
        )
        session.add(
            NodeRevisionEvidence(
                project_id=node.project_id,
                node_revision_id=revision.id,
                evidence_id=evidence.id,
                support_type=spec.support_type,
            )
        )
        # Transitional read projection for the existing embedding/review code.
        upsert_node_evidence(
            session,
            node_id=node.id,
            segment_id=spec.source_segment_id or "user-assertion",
            quote=spec.quoted_text,
            quote_start=spec.quote_start,
            quote_end=spec.quote_end,
            evidence_type=spec.source_type,
            source_meeting_id=spec.external_meeting_id,
        )

    node.title = title
    node.content = content
    node.node_type = node_type
    node.category = category
    node.due_date = due_date
    node.version = next_version
    node.current_revision_id = revision.id
    node.last_actor_type = created_by_type
    node.updated_at = datetime.now(timezone.utc)
    session.flush()
    return revision


def current_revision_evidence_specs(session, *, node: Node) -> list[EvidenceSpec]:
    if node.current_revision_id is None:
        return []
    rows = session.execute(
        select(NodeRevisionEvidence, Evidence)
        .join(
            Evidence,
            Evidence.id == NodeRevisionEvidence.evidence_id,
        )
        .where(
            NodeRevisionEvidence.project_id == node.project_id,
            NodeRevisionEvidence.node_revision_id == node.current_revision_id,
            Evidence.project_id == node.project_id,
        )
    ).all()
    return [
        EvidenceSpec(
            external_meeting_id=evidence.external_meeting_id,
            transcript_segment_id=evidence.transcript_segment_id,
            source_segment_id=evidence.source_segment_id,
            speaker_label=evidence.speaker_label,
            start_ms=evidence.start_ms,
            end_ms=evidence.end_ms,
            quote_start=evidence.quote_start,
            quote_end=evidence.quote_end,
            quoted_text=evidence.quoted_text,
            source_type=evidence.source_type,
            normalization_version=evidence.normalization_version,
            support_type=link.support_type,
            legacy_imported=evidence.legacy_imported,
        )
        for link, evidence in rows
    ]


def mark_node_embedding_stale(session, *, node: Node) -> None:
    """Unconditionally invalidate this Node's READY embeddings.

    Prefer :func:`reconcile_embedding_status_after_revision`; this stays for the
    few call sites that must invalidate regardless of the meaning hash (for
    example when the Node identity itself moves, as in a logical merge source).
    """

    for embedding in session.execute(
        select(NodeEmbedding).where(
            NodeEmbedding.node_id == node.id,
            NodeEmbedding.status == "READY",
        )
    ).scalars():
        embedding.status = "STALE"


@dataclass(frozen=True)
class EmbeddingInvalidationResult:
    """What reconciliation decided for one Node's embeddings."""

    invalidated: int
    kept_ready: int
    current_hash: str | None
    reason: str

    @property
    def reembedding_required(self) -> bool:
        return self.invalidated > 0


def reconcile_embedding_status_after_revision(
    session,
    *,
    node: Node,
) -> EmbeddingInvalidationResult:
    """Invalidate embeddings only when the v2 meaning hash actually changed.

    Category-only, due-date-only and evidence-reordering edits
    all produce the identical canonical v2 text, so their vectors stay READY and
    no provider call is ever made. title/content/node_type/evidence changes move
    the hash and mark the row STALE.

    Must run inside the caller's transaction, after the new Revision is flushed.
    """

    from data_pipeline.retrieval.embedding import (
        CurrentRevisionEmbeddingError,
        load_current_revision_embedding_input,
    )

    rows = list(
        session.execute(
            select(NodeEmbedding).where(NodeEmbedding.node_id == node.id)
        ).scalars()
    )
    ready = [row for row in rows if row.status == "READY"]
    if not ready:
        return EmbeddingInvalidationResult(0, 0, None, "NO_READY_EMBEDDING")

    try:
        current = load_current_revision_embedding_input(session, node=node)
    except CurrentRevisionEmbeddingError as exc:
        # Cannot prove the vector still matches the Node: fail safe to STALE.
        for row in ready:
            row.status = "STALE"
        return EmbeddingInvalidationResult(len(ready), 0, None, exc.reason)

    invalidated = kept = 0
    for row in ready:
        if row.embedded_text_hash == current.text_hash:
            kept += 1
        else:
            row.status = "STALE"
            invalidated += 1
    return EmbeddingInvalidationResult(
        invalidated=invalidated,
        kept_ready=kept,
        current_hash=current.text_hash,
        reason="HASH_CHANGED" if invalidated else "HASH_UNCHANGED",
    )


__all__ = [
    "EmbeddingInvalidationResult",
    "EvidenceSpec",
    "create_node_revision",
    "current_revision_evidence_specs",
    "evidence_hash",
    "mark_node_embedding_stale",
    "reconcile_embedding_status_after_revision",
    "user_assertion_evidence",
    "validated_candidate_evidence",
]
