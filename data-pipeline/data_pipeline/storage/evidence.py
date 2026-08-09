"""Deterministic NodeEvidence identity and dialect-safe idempotent insert."""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import NodeEvidence

EVIDENCE_KEY_VERSION = "node-evidence-v1"


def build_evidence_key(
    *,
    segment_id: str,
    quote: str,
    quote_start: int | None,
    quote_end: int | None,
    evidence_type: str | None,
    source_meeting_id: str | None,
) -> str:
    """Hash every provenance field except node_id, which is in the DB key."""

    canonical = json.dumps(
        [
            EVIDENCE_KEY_VERSION,
            source_meeting_id,
            segment_id,
            quote_start,
            quote_end,
            quote,
            evidence_type,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upsert_node_evidence(
    session: Session,
    *,
    node_id: uuid.UUID,
    segment_id: str,
    quote: str,
    quote_start: int | None,
    quote_end: int | None,
    evidence_type: str | None,
    source_meeting_id: str | None,
) -> bool:
    """Insert one Evidence row or ignore the same (node_id, evidence_key)."""

    evidence_key = build_evidence_key(
        segment_id=segment_id,
        quote=quote,
        quote_start=quote_start,
        quote_end=quote_end,
        evidence_type=evidence_type,
        source_meeting_id=source_meeting_id,
    )
    values = {
        "id": uuid.uuid4(),
        "node_id": node_id,
        "evidence_key": evidence_key,
        "segment_id": segment_id,
        "quote": quote,
        "quote_start": quote_start,
        "quote_end": quote_end,
        "evidence_type": evidence_type,
        "source_meeting_id": source_meeting_id,
    }
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = postgresql_insert(NodeEvidence).values(**values)
        statement = statement.on_conflict_do_nothing(
            index_elements=["node_id", "evidence_key"],
        )
        return session.execute(statement).rowcount == 1
    if dialect_name == "sqlite":
        statement = sqlite_insert(NodeEvidence).values(**values)
        statement = statement.on_conflict_do_nothing(
            index_elements=["node_id", "evidence_key"],
        )
        return session.execute(statement).rowcount == 1

    existing = session.scalar(
        select(NodeEvidence.id).where(
            NodeEvidence.node_id == node_id,
            NodeEvidence.evidence_key == evidence_key,
        )
    )
    if existing is not None:
        return False
    session.add(NodeEvidence(**values))
    return True
