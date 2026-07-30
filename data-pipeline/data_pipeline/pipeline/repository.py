"""DB 접근 헬퍼 (읽기 + 기존 노드 시딩). 규칙 7 사전 감지용 시그니처 조회 포함."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_pipeline.contracts.enums import GraphState, default_lifecycle_status
from data_pipeline.storage.models import (
    Meeting,
    Node,
    NodeCandidate,
    NodeCandidateEvidence,
    Request,
    TranscriptSegment,
)
from data_pipeline.storage.evidence import upsert_node_evidence
from data_pipeline.validation import SegmentInfo, resolve_item_evidence
from data_pipeline.validation.plan import title_evidence_signature

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_ALLOWED_CANDIDATE_NODE_TYPES = {"DECISION", "ACTION", "ISSUE"}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_identifier(value: object, *, prefix: str, position: int = 0) -> str:
    raw = "" if value is None else str(value)
    if _SAFE_ID.fullmatch(raw):
        return raw
    return f"{prefix}-{position + 1}-{_canonical_hash({'position': position, 'value': raw})[:16]}"


def normalize_extraction_items(raw_items: list[dict]) -> list[dict]:
    """Preserve every item while assigning deterministic, unique server IDs."""

    normalized: list[dict] = []
    used: set[str] = set()
    for position, raw_item in enumerate(raw_items):
        item = dict(raw_item)
        candidate_id = _safe_identifier(item.get("id"), prefix="item", position=position)
        if candidate_id in used:
            candidate_id = (
                f"item-{position + 1}-"
                f"{_canonical_hash({'position': position, 'item': raw_item})[:16]}"
            )
        while candidate_id in used:
            candidate_id = f"item-{position + 1}-{_canonical_hash(candidate_id)[:16]}"
        item["id"] = candidate_id
        used.add(candidate_id)
        normalized.append(item)
    return normalized


def _candidate_node_type(value: object) -> str:
    normalized = str(value or "").upper()
    return normalized if normalized in _ALLOWED_CANDIDATE_NODE_TYPES else "UNKNOWN"


def _bounded_category(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value)
    return normalized[:64] or None


def get_node(session: Session, node_id: str) -> Node | None:
    try:
        pk = uuid.UUID(str(node_id))
    except (ValueError, TypeError):
        return None
    return session.get(Node, pk)


def upsert_meeting(session: Session, project_id: str, external_meeting_id: str) -> Meeting:
    existing = session.execute(
        select(Meeting).where(
            Meeting.project_id == project_id,
            Meeting.external_meeting_id == external_meeting_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    meeting = Meeting(project_id=project_id, external_meeting_id=external_meeting_id, status="AI_PROCESSING")
    session.add(meeting)
    session.flush()
    return meeting


def upsert_segments(session: Session, project_id: str, external_meeting_id: str, segments: list[dict]) -> int:
    """세그먼트 저장 (UNIQUE 로 멱등). 이미 있으면 건너뛴다. 반환: 새로 삽입한 수."""
    have = set(
        session.execute(
            select(TranscriptSegment.segment_id).where(
                TranscriptSegment.project_id == project_id,
                TranscriptSegment.external_meeting_id == external_meeting_id,
            )
        ).scalars()
    )
    inserted = 0
    for position, seg in enumerate(segments):
        sid = seg.get("segmentId")
        if not sid or sid in have:
            continue
        raw_text = str(seg.get("rawText", seg.get("text", "")))
        normalized_text = str(
            seg.get("normalizedText", seg.get("text", raw_text))
        )
        session.add(TranscriptSegment(
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            segment_id=sid,
            sequence_no=seg.get("sequenceNo", position),
            start_ms=seg.get("startMs"),
            end_ms=seg.get("endMs"),
            speaker_label=seg.get("speakerLabel"),
            text=normalized_text,
            text_hash=hashlib.sha256(
                normalized_text.encode("utf-8")
            ).hexdigest(),
            raw_text=raw_text,
            raw_text_hash=hashlib.sha256(
                raw_text.encode("utf-8")
            ).hexdigest(),
            normalized_text=normalized_text,
            normalization_metadata=seg.get("normalization"),
        ))
        have.add(sid)
        inserted += 1
    return inserted


def list_candidates_for_request(session: Session, request_id: uuid.UUID) -> list[NodeCandidate]:
    return list(
        session.execute(
            select(NodeCandidate)
            .where(NodeCandidate.request_id == request_id)
            .order_by(NodeCandidate.created_at, NodeCandidate.source_item_id)
        ).scalars()
    )


def get_candidate_for_review(
    session: Session,
    candidate_id: str | uuid.UUID,
    *,
    for_update: bool = False,
) -> NodeCandidate | None:
    try:
        parsed_id = (
            candidate_id
            if isinstance(candidate_id, uuid.UUID)
            else uuid.UUID(str(candidate_id))
        )
    except (TypeError, ValueError):
        return None
    statement = (
        select(NodeCandidate)
        .options(selectinload(NodeCandidate.evidence))
        .where(NodeCandidate.id == parsed_id)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def query_candidates_for_review(
    session: Session,
    *,
    project_id: str,
    external_meeting_id: str | None = None,
    request_id: str | uuid.UUID | None = None,
    review_status: str | None = None,
    suggested_disposition: str | None = None,
) -> list[NodeCandidate]:
    statement = (
        select(NodeCandidate)
        .join(Request, Request.id == NodeCandidate.request_id)
        .options(selectinload(NodeCandidate.evidence))
        .where(NodeCandidate.project_id == project_id)
        .order_by(NodeCandidate.created_at, NodeCandidate.source_item_id)
    )
    if external_meeting_id is not None:
        statement = statement.where(
            NodeCandidate.external_meeting_id == external_meeting_id
        )
    if request_id is not None:
        try:
            parsed_request_id = (
                request_id
                if isinstance(request_id, uuid.UUID)
                else uuid.UUID(str(request_id))
            )
        except (TypeError, ValueError):
            statement = statement.where(Request.external_request_id == str(request_id))
        else:
            statement = statement.where(NodeCandidate.request_id == parsed_request_id)
    if review_status is not None:
        statement = statement.where(NodeCandidate.review_status == review_status)
    if suggested_disposition is not None:
        statement = statement.where(
            NodeCandidate.suggested_disposition == suggested_disposition
        )
    return list(session.execute(statement).scalars().unique())


def update_request_generation_metadata(
    request: Request,
    *,
    lineage: dict,
    usage: dict,
    raw_extraction: dict | list | str | None,
    raw_judgment: dict | list | str | None,
    completed_at: datetime,
) -> None:
    request.lineage = lineage
    request.usage = usage
    request.raw_extraction = raw_extraction
    request.raw_judgment = raw_judgment
    request.completed_at = completed_at


def create_generation_candidates(
    session: Session,
    *,
    request: Request,
    project_id: str,
    external_meeting_id: str,
    items: list[dict],
    raw_items: list[dict] | None,
    raw_judgments: list[dict],
    validated_judgments: list[dict],
    segments: dict[str, SegmentInfo],
    allowed_existing_node_ids: set[str],
) -> list[NodeCandidate]:
    """Insert every item, then resolve same-meeting parent references by UUID."""

    validated_by_item = {str(row.get("itemId")): row for row in validated_judgments}
    raw_by_item: dict[str, dict] = {}
    for row in raw_judgments:
        raw_by_item.setdefault(str(row.get("itemId")), dict(row))

    rows: list[NodeCandidate] = []
    by_source_item: dict[str, NodeCandidate] = {}
    preserved_items = raw_items if raw_items is not None else items
    if len(preserved_items) != len(items):
        raise ValueError("raw_items and items must have the same length")

    for item, raw_item in zip(items, preserved_items, strict=True):
        item_id = str(item.get("id"))
        judgment = validated_by_item[item_id]
        row = NodeCandidate(
            request_id=request.id,
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            source_item_id=item_id,
            raw_item=dict(raw_item),
            raw_judgment=raw_by_item.get(item_id),
            suggested_node_type=_candidate_node_type(item.get("type")),
            suggested_category=_bounded_category(
                judgment.get("category") or item.get("predictedCategory")
            ),
            suggested_title=str(item.get("title") or ""),
            suggested_content=str(item.get("content") or ""),
            suggested_disposition=str(judgment.get("result")),
            suggested_reason=judgment.get("reason"),
            review_status="PENDING",
        )
        session.add(row)
        rows.append(row)
        by_source_item[item_id] = row

    session.flush()

    for row in rows:
        judgment = validated_by_item[row.source_item_id]
        if str(judgment.get("result")) != "ATTACH":
            continue
        target = str(judgment.get("attachTo"))
        same_meeting_parent = by_source_item.get(target)
        if same_meeting_parent is not None:
            row.suggested_parent_candidate_id = same_meeting_parent.id
            continue
        if target not in allowed_existing_node_ids:
            continue
        existing = get_node(session, target)
        if existing is not None:
            row.suggested_parent_node_id = existing.id

    for item, row in zip(items, rows, strict=True):
        for evidence in item.get("evidence") or []:
            segment_id = evidence.get("segmentId")
            if not segment_id:
                continue
            resolution = resolve_item_evidence(
                {"id": row.source_item_id, "evidence": [evidence]},
                segments,
            )
            resolved = resolution.resolved[0] if resolution.resolved else None
            session.add(NodeCandidateEvidence(
                candidate_id=row.id,
                segment_id=_safe_identifier(segment_id, prefix="segment"),
                quote=str(evidence.get("quote") or ""),
                quote_start=resolved.char_start if resolved else None,
                quote_end=resolved.char_end if resolved else None,
                evidence_type="MEETING",
                source_meeting_id=external_meeting_id,
            ))
    session.flush()
    return rows


def existing_source_keys(session: Session, project_id: str) -> set[tuple[str, str, str]]:
    rows = session.execute(
        select(Node.project_id, Node.source_meeting_id, Node.source_item_id).where(
            Node.project_id == project_id
        )
    ).all()
    return {(r[0], r[1], r[2]) for r in rows}


def existing_title_evidence_signatures(session: Session, project_id: str) -> set[tuple[str, tuple[str, ...]]]:
    """규칙 7: 동일 제목·근거 노드 감지용. (정규화 제목, 정렬된 segmentId 집합)."""
    sigs: set[tuple[str, tuple[str, ...]]] = set()
    nodes = session.execute(select(Node).where(Node.project_id == project_id)).scalars().all()
    for node in nodes:
        seg_ids = tuple(sorted({ev.segment_id for ev in node.evidence}))
        from data_pipeline.validation.normalize import normalize_quote

        sigs.add((normalize_quote(node.title or ""), seg_ids))
    return sigs


# --- 기존 노드 시딩 (이전 회의 산출물 모사 — 후보/UPDATE 대상 준비) ------------
def seed_node(
    session: Session,
    *,
    project_id: str,
    source_meeting_id: str,
    source_item_id: str,
    node_type: str,
    category: str,
    title: str,
    content: str = "",
    parent_id: str | None = None,
    lifecycle_status: str | None = None,
    graph_state: str = GraphState.ACTIVE.value,
    version: int = 1,
    due_date: str | None = None,
    evidence: list[dict] | None = None,
) -> Node:
    node = Node(
        project_id=project_id,
        source_meeting_id=source_meeting_id,
        source_item_id=source_item_id,
        node_type=node_type,
        category=category,
        title=title,
        content=content,
        parent_id=uuid.UUID(parent_id) if parent_id else None,
        graph_state=graph_state,
        lifecycle_status=lifecycle_status or default_lifecycle_status(node_type),
        version=version,
        due_date=due_date,
    )
    session.add(node)
    session.flush()
    for ev in evidence or []:
        upsert_node_evidence(
            session,
            node_id=node.id,
            segment_id=ev.get("segmentId"),
            quote=ev.get("quote", ""),
            quote_start=ev.get("quoteStart"),
            quote_end=ev.get("quoteEnd"),
            evidence_type="MEETING",
            source_meeting_id=source_meeting_id,
        )
    session.flush()
    return node
