"""Idempotently seed the synthetic gold graph through ORM/service boundaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select

from data_pipeline.pipeline.revisions import EvidenceSpec, create_node_revision
from data_pipeline.storage import (
    Meeting,
    Node,
    Relation,
    TranscriptSegment,
)

from .labels import build_gold_labels
from .scenarios import (
    DATASET_VERSION,
    ISOLATION_PROJECT_ID,
    MAIN_PROJECT_ID,
    SyntheticNodeSpec,
    build_isolation_nodes,
    build_synthetic_cases,
    build_synthetic_nodes,
    stable_uuid,
)


@dataclass(frozen=True)
class SyntheticSeedReport:
    dataset_version: str
    created_nodes: int
    reused_nodes: int
    created_meetings: int
    created_segments: int
    created_relations: int
    main_node_count: int
    isolation_node_count: int
    gold_case_count: int

    def as_dict(self) -> dict:
        return {
            "datasetVersion": self.dataset_version,
            "createdNodes": self.created_nodes,
            "reusedNodes": self.reused_nodes,
            "createdMeetings": self.created_meetings,
            "createdSegments": self.created_segments,
            "createdRelations": self.created_relations,
            "mainNodeCount": self.main_node_count,
            "isolationNodeCount": self.isolation_node_count,
            "goldCaseCount": self.gold_case_count,
        }


def _ensure_meeting(session, spec: SyntheticNodeSpec) -> tuple[Meeting, bool]:
    meeting = session.execute(
        select(Meeting).where(
            Meeting.project_id == spec.project_id,
            Meeting.external_meeting_id == spec.meeting_id,
        )
    ).scalar_one_or_none()
    if meeting is not None:
        return meeting, False
    meeting = Meeting(
        id=stable_uuid(spec.project_id, "meeting", spec.meeting_id),
        project_id=spec.project_id,
        external_meeting_id=spec.meeting_id,
        status="COMPLETED",
    )
    session.add(meeting)
    session.flush()
    return meeting, True


def _ensure_segment(
    session,
    spec: SyntheticNodeSpec,
    sequence_no: int,
) -> tuple[TranscriptSegment, bool]:
    segment = session.execute(
        select(TranscriptSegment).where(
            TranscriptSegment.project_id == spec.project_id,
            TranscriptSegment.external_meeting_id == spec.meeting_id,
            TranscriptSegment.segment_id == spec.segment_id,
        )
    ).scalar_one_or_none()
    if segment is not None:
        return segment, False
    text_hash = hashlib.sha256(spec.quote.encode("utf-8")).hexdigest()
    segment = TranscriptSegment(
        id=stable_uuid(spec.project_id, "segment", spec.key),
        project_id=spec.project_id,
        external_meeting_id=spec.meeting_id,
        segment_id=spec.segment_id,
        sequence_no=sequence_no,
        start_ms=sequence_no * 10_000,
        end_ms=sequence_no * 10_000 + 8_000,
        speaker_label=f"speaker-{(sequence_no % 4) + 1}",
        text=spec.quote,
        text_hash=text_hash,
        raw_text=spec.quote,
        raw_text_hash=text_hash,
        normalized_text=spec.quote,
        normalization_metadata={
            "dictionary_version": DATASET_VERSION,
            "synthetic": True,
        },
    )
    session.add(segment)
    session.flush()
    return segment, True


def _ensure_node(
    session,
    *,
    spec: SyntheticNodeSpec,
    sequence_no: int,
    node_ids: dict[str, object],
) -> tuple[Node, bool, bool, bool]:
    existing = session.get(Node, spec.node_id)
    if existing is not None:
        if (
            existing.project_id != spec.project_id
            or existing.node_type != spec.node_type
            or existing.title != spec.title
            or existing.content != spec.content
            or existing.graph_state != spec.graph_state
        ):
            raise ValueError(
                f"deterministic synthetic Node conflicts with {spec.key}"
            )
        return existing, False, False, False
    _, meeting_created = _ensure_meeting(session, spec)
    segment, segment_created = _ensure_segment(session, spec, sequence_no)
    parent_id = node_ids.get(spec.parent_key) if spec.parent_key else None
    node = Node(
        id=spec.node_id,
        project_id=spec.project_id,
        source_meeting_id=spec.meeting_id,
        source_item_id=spec.source_item_id,
        node_type=spec.node_type,
        category=spec.category,
        title=spec.title,
        content=spec.content,
        parent_id=parent_id,
        graph_state=spec.graph_state,
        analysis_status="PENDING",
        version=1,
        origin_type="USER_CREATED",
        last_actor_type="SYSTEM",
        consistency_status="NORMAL",
    )
    session.add(node)
    session.flush()
    create_node_revision(
        session,
        node=node,
        title=spec.title,
        content=spec.content,
        node_type=spec.node_type,
        category=spec.category,
        due_date=None,
        created_by_type="SYSTEM",
        created_by_id="SYNTHETIC_GOLD_SEED",
        generation_run_id=None,
        evidence_specs=[
            EvidenceSpec(
                external_meeting_id=spec.meeting_id,
                transcript_segment_id=segment.id,
                source_segment_id=segment.segment_id,
                speaker_label=segment.speaker_label,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                quote_start=0,
                quote_end=len(spec.quote),
                quoted_text=spec.quote,
                source_type="TRANSCRIPT",
                normalization_version=DATASET_VERSION,
                support_type="PRIMARY",
            )
        ],
        requires_evidence=True,
    )
    return node, True, meeting_created, segment_created


def seed_synthetic_evaluation(session) -> SyntheticSeedReport:
    canonical = build_synthetic_nodes()
    cases = build_synthetic_cases()
    isolation = build_isolation_nodes()
    specs = canonical + [case.source for case in cases] + isolation
    node_ids = {spec.key: spec.node_id for spec in specs}
    created_nodes = reused_nodes = created_meetings = created_segments = 0
    created_relations = 0
    meeting_sequences: dict[tuple[str, str], int] = {}

    # Parent Decisions are listed before dependent canonical Nodes.
    for spec in specs:
        sequence_key = (spec.project_id, spec.meeting_id)
        meeting_sequences[sequence_key] = meeting_sequences.get(sequence_key, 0) + 1
        _, created, meeting_created, segment_created = _ensure_node(
            session,
            spec=spec,
            sequence_no=meeting_sequences[sequence_key],
            node_ids=node_ids,
        )
        created_nodes += int(created)
        reused_nodes += int(not created)
        created_meetings += int(meeting_created)
        created_segments += int(segment_created)

    for spec in specs:
        if spec.parent_key is None or spec.graph_state != "ACTIVE":
            continue
        parent_id = node_ids[spec.parent_key]
        relation = session.execute(
            select(Relation).where(
                Relation.project_id == spec.project_id,
                Relation.from_node_id == spec.node_id,
                Relation.to_node_id == parent_id,
                Relation.relation_type == "ATTACHED_TO",
            )
        ).scalar_one_or_none()
        if relation is None:
            session.add(
                Relation(
                    id=stable_uuid(spec.project_id, "relation", spec.key),
                    project_id=spec.project_id,
                    from_node_id=spec.node_id,
                    to_node_id=parent_id,
                    relation_type="ATTACHED_TO",
                    status="CONFIRMED",
                    actor_type="SYSTEM",
                )
            )
            created_relations += 1

    session.flush()
    main_count = session.execute(
        select(func.count(Node.id)).where(Node.project_id == MAIN_PROJECT_ID)
    ).scalar_one()
    isolation_count = session.execute(
        select(func.count(Node.id)).where(
            Node.project_id == ISOLATION_PROJECT_ID
        )
    ).scalar_one()
    labels = build_gold_labels(cases)
    if len({row.case_id for row in labels}) != len(labels):
        raise ValueError("synthetic gold case IDs are not unique")
    return SyntheticSeedReport(
        dataset_version=DATASET_VERSION,
        created_nodes=created_nodes,
        reused_nodes=reused_nodes,
        created_meetings=created_meetings,
        created_segments=created_segments,
        created_relations=created_relations,
        main_node_count=main_count,
        isolation_node_count=isolation_count,
        gold_case_count=len(labels),
    )


__all__ = ["SyntheticSeedReport", "seed_synthetic_evaluation"]
