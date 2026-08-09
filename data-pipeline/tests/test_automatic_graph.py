from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from data_pipeline.api.graph_services import create_relation
from data_pipeline.api.graph_services import get_graph_node_view
from data_pipeline.config import RetrievalSettings
import data_pipeline.pipeline.automatic_graph as automatic_graph_module
from data_pipeline.pipeline.automatic_graph import (
    AutoMergePolicy,
    _deduplicate_evidence_specs,
    _resolve_existing_parent_canonical_id,
    _set_run_stage,
    _source_request_and_candidates,
    apply_graph_mutation_plan,
    build_graph_mutation_plan,
    run_automatic_graph,
    run_automatic_meeting,
)
from data_pipeline.pipeline.graph import (
    list_canonical_relations,
    resolve_canonical_node,
    unmerge_operation,
)
from data_pipeline.pipeline.errors import (
    GraphMutationValidationError,
    MergeNotReversibleError,
)
from data_pipeline.pipeline.user_graph import (
    create_user_node,
    edit_node,
    user_merge_nodes,
)
from data_pipeline.pipeline.revisions import EvidenceSpec
from data_pipeline.storage import (
    AnalysisDeliveryState,
    Evidence,
    GenerationRun,
    Meeting,
    MergeOperation,
    Node,
    NodeCandidate,
    NodeCandidateEvidence,
    NodeEmbedding,
    NodeRevision,
    NodeRevisionEvidence,
    OutboxEvent,
    Relation,
    Request,
    TranscriptSegment,
)
from data_pipeline.worker.fakes import FakeMeetingChatClient
from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION


class UnitEmbedding:
    def embed(self, *, text: str, model: str, dimensions: int):
        del text, model
        return [1.0] + [0.0] * (dimensions - 1)


class TypeEmbedding:
    def embed(self, *, text: str, model: str, dimensions: int):
        node_type = text.lstrip().split('"')[1]
        if node_type == "ACTION":
            return [0.0, 1.0, 0.0] + [0.0] * (dimensions - 3)
        if node_type == "ISSUE":
            return [0.0, 0.0, 1.0] + [0.0] * (dimensions - 3)
        return [1.0, 0.0, 0.0] + [0.0] * (dimensions - 3)


class GroupAwareEmbedding(TypeEmbedding):
    def embed(self, *, text: str, model: str, dimensions: int):
        if '"ACTION"' in text and "group-b" in text:
            return [0.0, 0.0, 1.0] + [0.0] * (dimensions - 3)
        return super().embed(
            text=text,
            model=model,
            dimensions=dimensions,
        )


class CreateOnlyB:
    provider_model = "fake-b-model"

    def recommend(self, *, source_node, retrieval_candidates):
        del retrieval_candidates
        return {
            "recommendation": "CREATE_NEW",
            "targetNodeId": None,
            "relationType": None,
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "distinct item",
            "metadata": {},
        }


class ExistingParentLinkB:
    provider_model = "fake-b-model"

    def __init__(self, parent_id: uuid.UUID):
        self.parent_id = parent_id

    def recommend(self, *, source_node, retrieval_candidates):
        parent = next(
            row
            for row in retrieval_candidates
            if row["nodeId"] == str(self.parent_id)
        )
        assert parent["nodeType"] == "DECISION"
        assert parent["category"] == source_node["category"]
        return {
            "recommendation": "LINK",
            "targetNodeId": parent["nodeId"],
            "relationType": "ATTACHED_TO",
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "existing Decision is the structural parent",
            "metadata": {},
        }


class DecisionMergeAndParentLinkB:
    provider_model = "fake-b-model"

    def __init__(self, target_id: uuid.UUID):
        self.target_id = target_id

    def recommend(self, *, source_node, retrieval_candidates):
        if source_node["nodeType"] == "DECISION":
            return {
                "recommendation": "MERGE",
                "targetNodeId": str(self.target_id),
                "relationType": None,
                "suggestedTitle": source_node["title"],
                "suggestedContent": source_node["content"],
                "reason": "same decision identity",
                "metadata": {
                    "confidence": 0.99,
                    "identityBasis": {
                        "same_subject": True,
                        "same_outcome_or_task": True,
                        "same_scope": True,
                        "same_time_or_scope": True,
                    },
                    "conflictsChecked": [
                        {"field": "scope", "result": "PASS"}
                    ],
                },
            }
        parent = next(
            row
            for row in retrieval_candidates
            if row.get("sameMeetingSuggestedParent")
        )
        return {
            "recommendation": "LINK",
            "targetNodeId": parent["nodeId"],
            "relationType": "ATTACHED_TO",
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "same-meeting Decision is the structural parent",
            "metadata": {},
        }


class DecisionMergeAfterConcurrentEditB(DecisionMergeAndParentLinkB):
    provider_model = "fake-b-model"

    def __init__(self, target_id: uuid.UUID, session_factory):
        super().__init__(target_id)
        self.session_factory = session_factory
        self.edited = False

    def recommend(self, *, source_node, retrieval_candidates):
        if not self.edited:
            with self.session_factory() as session:
                target = session.get(Node, self.target_id)
                version = target.version
                project_id = target.project_id
            edit_node(
                self.session_factory,
                project_id=project_id,
                node_id=self.target_id,
                actor_id="concurrent-user",
                request_id="concurrent-target-edit",
                expected_version=version,
                content="사용자가 자동 판단 도중 변경한 내용",
            )
            self.edited = True
        return super().recommend(
            source_node=source_node,
            retrieval_candidates=retrieval_candidates,
        )


def _identity_metadata(*, action: bool) -> dict:
    identity = {
        "same_subject": True,
        "same_outcome_or_task": True,
        "same_scope": True,
        "same_time_or_scope": True,
    }
    if action:
        identity["same_owner_if_required"] = True
    return {
        "confidence": 0.99,
        "identityBasis": identity,
        "conflictsChecked": [{"field": "identity", "result": "PASS"}],
    }


class DecisionAndActionMergeB:
    provider_model = "fake-b-model"

    def __init__(
        self,
        *,
        decision_target_id: uuid.UUID | None,
        action_target_id: uuid.UUID,
    ):
        self.decision_target_id = decision_target_id
        self.action_target_id = action_target_id

    def recommend(self, *, source_node, retrieval_candidates):
        del retrieval_candidates
        if source_node["nodeType"] == "DECISION":
            if self.decision_target_id is None:
                return {
                    "recommendation": "CREATE_NEW",
                    "targetNodeId": None,
                    "relationType": None,
                    "suggestedTitle": source_node["title"],
                    "suggestedContent": source_node["content"],
                    "reason": "new decision identity",
                    "metadata": {},
                }
            target_id = self.decision_target_id
            action = False
        else:
            target_id = self.action_target_id
            action = True
        return {
            "recommendation": "MERGE",
            "targetNodeId": str(target_id),
            "relationType": None,
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "same stable identity",
            "metadata": _identity_metadata(action=action),
        }


class DecisionAndMappedActionMergeB(DecisionAndActionMergeB):
    provider_model = "fake-b-model"

    def __init__(
        self,
        *,
        decision_target_id: uuid.UUID,
        action_target_a: uuid.UUID,
        action_target_b: uuid.UUID,
    ):
        super().__init__(
            decision_target_id=decision_target_id,
            action_target_id=action_target_a,
        )
        self.action_target_a = action_target_a
        self.action_target_b = action_target_b

    def recommend(self, *, source_node, retrieval_candidates):
        if source_node["nodeType"] == "ACTION":
            target_id = (
                self.action_target_b
                if "group-b" in source_node["title"]
                else self.action_target_a
            )
            return {
                "recommendation": "MERGE",
                "targetNodeId": str(target_id),
                "relationType": None,
                "suggestedTitle": source_node["title"],
                "suggestedContent": source_node["content"],
                "reason": "same mapped Action identity",
                "metadata": _identity_metadata(action=True),
            }
        return super().recommend(
            source_node=source_node,
            retrieval_candidates=retrieval_candidates,
        )


class SameTargetMergeB:
    provider_model = "fake-b-model"

    def __init__(self, target_id: uuid.UUID):
        self.target_id = target_id

    def recommend(self, *, source_node, retrieval_candidates):
        del retrieval_candidates
        return {
            "recommendation": "MERGE",
            "targetNodeId": str(self.target_id),
            "relationType": None,
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "same type identity",
            "metadata": _identity_metadata(
                action=source_node["nodeType"] == "ACTION"
            ),
        }


def _settings() -> RetrievalSettings:
    return RetrievalSettings(
        decision_top_k=3,
        node_top_k=5,
        min_similarity=None,
        embedding_model="text-embedding-3-small",
        embedding_version=EMBEDDING_CONTRACT_VERSION,
        embedding_dim=1536,
        config_version="automatic-test-v1",
    )


def _seed_request(session_factory, *, project: str, meeting: str):
    request_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            Meeting(
                project_id=project,
                external_meeting_id=meeting,
                status="AI_PROCESSING",
            )
        )
        request = Request(
            id=request_id,
            project_id=project,
            external_meeting_id=meeting,
            external_request_id=f"req-{meeting}",
            pipeline_version="node-generation-0.4.0",
            run_type="NODE_GENERATION",
            input_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            input_hash_version="test-v1",
            status="REVIEW_PENDING",
        )
        session.add(request)
        session.commit()
    return request_id


def _seed_candidate(
    session_factory,
    *,
    request_id: uuid.UUID,
    project: str,
    meeting: str,
    item_id: str,
    node_type: str,
    title: str,
    parent_candidate_id: uuid.UUID | None = None,
    valid_evidence: bool = True,
    start_ms: int = 100,
) -> uuid.UUID:
    candidate_id = uuid.uuid4()
    text = f"{title} 근거 발언"
    with session_factory() as session:
        segment = TranscriptSegment(
            project_id=project,
            external_meeting_id=meeting,
            segment_id=f"segment-{item_id}",
            sequence_no=int(item_id.rsplit("-", 1)[-1]),
            text=text,
            raw_text=text,
            normalized_text=text,
            speaker_label="speaker-1",
            start_ms=start_ms,
            end_ms=start_ms + 400,
        )
        session.add(segment)
        candidate = NodeCandidate(
            id=candidate_id,
            request_id=request_id,
            project_id=project,
            external_meeting_id=meeting,
            source_item_id=item_id,
            raw_item={"id": item_id, "type": node_type, "title": title},
            raw_judgment={"itemId": item_id, "result": "UNATTACHED"},
            suggested_node_type=node_type,
            suggested_category="BACKEND",
            suggested_title=title,
            suggested_content=f"{title} 내용",
            suggested_disposition="UNATTACHED",
            suggested_reason="test",
            suggested_parent_candidate_id=parent_candidate_id,
            review_status="PENDING",
        )
        session.add(candidate)
        session.add(
            NodeCandidateEvidence(
                candidate_id=candidate_id,
                segment_id=segment.segment_id,
                quote=text if valid_evidence else "존재하지 않는 인용",
                quote_start=0,
                quote_end=len(text),
                evidence_type="MEETING",
                source_meeting_id=meeting,
            )
        )
        session.commit()
    return candidate_id


def _seed_generation_run(
    session_factory,
    *,
    project: str,
    meeting: str,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            GenerationRun(
                id=run_id,
                project_id=project,
                external_meeting_id=meeting,
                recording_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                pipeline_version="node-generation-0.4.0",
                status="EXTRACTING",
            )
        )
        session.commit()
    return run_id


def _seed_existing_decision(
    session_factory,
    *,
    project: str,
    title: str,
) -> uuid.UUID:
    created = create_user_node(
        session_factory,
        project_id=project,
        actor_id="seed",
        request_id="seed",
        node_type="DECISION",
        category="BACKEND",
        title=title,
        content=f"{title} 기존 내용",
        due_date=None,
        evidence_assertion=f"{title} seed assertion",
        external_meeting_id=None,
    )
    with session_factory() as session:
        session.add(
            NodeEmbedding(
                node_id=created.node_id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                embedding=[1.0, 0.0, 0.0] + [0.0] * 1533,
                status="READY",
            )
        )
        session.commit()
    return created.node_id


def _seed_existing_action(
    session_factory,
    *,
    project: str,
    parent_id: uuid.UUID,
    title: str,
) -> uuid.UUID:
    created = create_user_node(
        session_factory,
        project_id=project,
        actor_id="seed",
        request_id=f"seed-{title}",
        node_type="ACTION",
        category="BACKEND",
        title=title,
        content=f"{title} existing content",
        due_date=None,
        evidence_assertion=f"{title} seed assertion",
        external_meeting_id=None,
    )
    with session_factory() as session:
        action_version = session.get(Node, created.node_id).version
        parent_version = session.get(Node, parent_id).version
    create_relation(
        session_factory,
        project_id=project,
        actor_id="seed",
        from_node_id=created.node_id,
        to_node_id=parent_id,
        relation_type="ATTACHED_TO",
        from_expected_version=action_version,
        to_expected_version=parent_version,
    )
    with session_factory() as session:
        session.add(
            NodeEmbedding(
                node_id=created.node_id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                embedding=[0.0, 1.0, 0.0] + [0.0] * 1533,
                status="READY",
            )
        )
        session.commit()
    return created.node_id


def _seed_existing_issue(
    session_factory,
    *,
    project: str,
    title: str,
) -> uuid.UUID:
    created = create_user_node(
        session_factory,
        project_id=project,
        actor_id="seed",
        request_id=f"seed-{title}",
        node_type="ISSUE",
        category="BACKEND",
        title=title,
        content=f"{title} existing content",
        due_date=None,
        evidence_assertion=f"{title} seed assertion",
        external_meeting_id=None,
    )
    with session_factory() as session:
        # Automatic MERGE targets must be ACTIVE canonical Nodes; create_user_node
        # yields UNATTACHED for ISSUE, so promote it to a realistic target state.
        session.get(Node, created.node_id).graph_state = "ACTIVE"
        session.add(
            NodeEmbedding(
                node_id=created.node_id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                embedding=[0.0, 0.0, 1.0] + [0.0] * 1533,
                status="READY",
            )
        )
        session.commit()
    return created.node_id


def _run_action_merge_scenario(
    session_factory,
    *,
    project: str,
    meeting: str,
    decision_target_id: uuid.UUID | None,
    action_target_id: uuid.UUID,
):
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    decision_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="meeting decision",
    )
    action_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-2",
        node_type="ACTION",
        title="repeat action",
        parent_candidate_id=decision_candidate_id,
    )
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[
            str(decision_candidate_id),
            str(action_candidate_id),
        ],
        embedding_client=TypeEmbedding(),
        b_model_client=DecisionAndActionMergeB(
            decision_target_id=decision_target_id,
            action_target_id=action_target_id,
        ),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
    )
    return result, run_id, decision_candidate_id, action_candidate_id


def _build_multi_action_merge_plan(
    session_factory,
    *,
    project: str,
    meeting: str,
    decision_target_id: uuid.UUID,
    action_target_id: uuid.UUID,
    action_inputs: list[tuple[str, int]],
):
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    decision_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="multi-source meeting decision",
        start_ms=10,
    )
    action_candidate_ids = []
    for item_id, start_ms in action_inputs:
        action_candidate_ids.append(
            _seed_candidate(
                session_factory,
                request_id=request_id,
                project=project,
                meeting=meeting,
                item_id=item_id,
                node_type="ACTION",
                title=f"repeat action {item_id}",
                parent_candidate_id=decision_candidate_id,
                start_ms=start_ms,
            )
        )
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )
    source_request_id, candidates, warnings = (
        _source_request_and_candidates(
            session_factory,
            project_id=project,
            external_meeting_id=meeting,
            candidate_ids=[
                str(decision_candidate_id),
                *(str(value) for value in action_candidate_ids),
            ],
        )
    )
    assert warnings == []
    plan = build_graph_mutation_plan(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        source_request_id=source_request_id,
        candidates=candidates,
        embedding_client=TypeEmbedding(),
        b_model_client=DecisionAndActionMergeB(
            decision_target_id=decision_target_id,
            action_target_id=action_target_id,
        ),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
        pipeline_label="automatic-b-model",
    )
    return (
        plan,
        run_id,
        decision_candidate_id,
        tuple(action_candidate_ids),
    )


def _run_multi_action_merge_scenario(
    session_factory,
    **kwargs,
):
    plan, run_id, decision_candidate_id, action_candidate_ids = (
        _build_multi_action_merge_plan(
            session_factory,
            **kwargs,
        )
    )
    _set_run_stage(
        session_factory,
        run_id=run_id,
        project_id=plan.project_id,
        status="VALIDATING",
    )
    result = apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )
    return (
        result,
        run_id,
        decision_candidate_id,
        action_candidate_ids,
    )


def test_automatic_graph_creates_revision_evidence_and_completion_outbox(
    session_factory,
):
    project, meeting = "project-auto", "meeting-auto"
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="자동 생성 결정",
    )
    generation_run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )

    result = run_automatic_graph(
        session_factory,
        generation_run_id=generation_run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(),
    )

    assert result.status in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
    assert len(result.created_node_ids) == 1
    with session_factory() as session:
        node = session.get(Node, result.created_node_ids[0])
        assert node.graph_state == "ACTIVE"
        assert node.current_revision_id is not None
        revision = session.get(NodeRevision, node.current_revision_id)
        assert revision.requires_evidence is True
        assert session.scalar(
            select(func.count(NodeRevisionEvidence.evidence_id)).where(
                NodeRevisionEvidence.node_revision_id == revision.id
            )
        ) == 1
        evidence = session.execute(select(Evidence)).scalar_one()
        assert evidence.source_type == "TRANSCRIPT"
        assert evidence.quoted_text == "자동 생성 결정 근거 발언"
        outbox = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED",
                OutboxEvent.aggregate_id == str(generation_run_id),
            )
        ).scalar_one()
        assert outbox.payload["createdCount"] == 1


def test_invalid_evidence_excludes_item_without_fabrication(session_factory):
    project, meeting = "project-invalid", "meeting-invalid"
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="잘못된 근거",
        valid_evidence=False,
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    assert result.created_node_ids == ()
    assert {
        warning["code"] for warning in result.warnings
    } >= {
        "INVALID_EVIDENCE_SPAN",
        "CANDIDATE_EXCLUDED_NO_VALID_EVIDENCE",
    }
    with session_factory() as session:
        assert session.scalar(select(func.count(Evidence.id))) == 0


def test_invalid_item_is_isolated_while_valid_item_is_published(
    session_factory,
):
    project, meeting = "project-isolated-item", "meeting-isolated-item"
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    invalid_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="제외될 결정",
        valid_evidence=False,
    )
    valid_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-2",
        node_type="DECISION",
        title="보존될 결정",
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(invalid_id), str(valid_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    assert result.status == "COMPLETED_WITH_WARNINGS"
    assert len(result.created_node_ids) == 1
    with session_factory() as session:
        node = session.get(Node, result.created_node_ids[0])
        assert node.source_candidate_id == valid_id
        run = session.get(GenerationRun, run_id)
        assert run.result_summary["warningCount"] >= 1
        assert run.result_summary["createdCount"] == 1


def test_parentless_action_is_preserved_as_unattached(session_factory):
    project, meeting = "project-parentless", "meeting-parentless"
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="ACTION",
        title="부모를 찾지 못한 작업",
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    with session_factory() as session:
        node = session.get(Node, result.created_node_ids[0])
        run = session.get(GenerationRun, run_id)
        assert node.graph_state == "UNATTACHED"
        assert node.parent_id is None
        assert run.result_summary["unattachedCount"] == 1


def test_action_can_link_to_an_existing_same_category_parent(session_factory):
    project = "project-existing-parent-link"
    meeting = "meeting-existing-parent-link"
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="existing parent",
    )
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="ACTION",
        title="action linked to existing parent",
    )
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )

    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=TypeEmbedding(),
        b_model_client=ExistingParentLinkB(parent_id),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(min_similarity=0.9, min_margin=0.1),
    )

    assert len(result.relation_ids) == 1
    with session_factory() as session:
        child = session.execute(
            select(Node).where(Node.source_candidate_id == candidate_id)
        ).scalar_one()
        assert child.graph_state == "ACTIVE"
        assert child.parent_id == parent_id


def test_uncalibrated_merge_is_downgraded_to_create_new(session_factory):
    project, meeting = "project-gate", "meeting-gate"
    target_id = _seed_existing_decision(
        session_factory, project=project, title="기존 결정"
    )
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="동일 결정",
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=DecisionMergeAndParentLinkB(target_id),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(),
    )
    with session_factory() as session:
        source = session.get(Node, result.created_node_ids[0])
        assert source.graph_state == "ACTIVE"
        assert source.merged_into_node_id is None
        assert session.scalar(select(func.count(MergeOperation.id))) == 0
    assert "MERGE_POLICY_UNCALIBRATED" in {
        warning["code"] for warning in result.warnings
    }


def test_concurrent_target_edit_downgrades_stale_merge(session_factory):
    project, meeting = "project-stale-target", "meeting-stale-target"
    target_id = _seed_existing_decision(
        session_factory, project=project, title="동시 수정 대상"
    )
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="동시 수정 대상",
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=UnitEmbedding(),
        b_model_client=DecisionMergeAfterConcurrentEditB(
            target_id, session_factory
        ),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
    )
    assert result.merge_operation_ids == ()
    assert "MERGE_TARGET_VERSION_CHANGED_CREATE_NEW" in {
        warning["code"] for warning in result.warnings
    }
    with session_factory() as session:
        source = session.get(Node, result.created_node_ids[0])
        target = session.get(Node, target_id)
        assert source.graph_state == "ACTIVE"
        assert source.merged_into_node_id is None
        assert target.content == "사용자가 자동 판단 도중 변경한 내용"


def test_decision_merge_preserves_dependent_action_parent(session_factory):
    project, meeting = "project-parent", "meeting-parent"
    existing_decision_id = _seed_existing_decision(
        session_factory, project=project, title="기존 canonical 결정"
    )
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    decision_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="병합될 결정",
    )
    action_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-2",
        node_type="ACTION",
        title="하위 Action",
        parent_candidate_id=decision_candidate_id,
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[
            str(decision_candidate_id),
            str(action_candidate_id),
        ],
        embedding_client=UnitEmbedding(),
        b_model_client=DecisionMergeAndParentLinkB(existing_decision_id),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
    )
    assert len(result.merge_operation_ids) == 1
    with session_factory() as session:
        decision = session.execute(
            select(Node).where(Node.source_candidate_id == decision_candidate_id)
        ).scalar_one()
        action = session.execute(
            select(Node).where(Node.source_candidate_id == action_candidate_id)
        ).scalar_one()
        relation = session.execute(
            select(Relation).where(
                Relation.from_node_id == action.id,
                Relation.relation_type == "ATTACHED_TO",
                Relation.status == "CONFIRMED",
            )
        ).scalar_one()
        assert decision.graph_state == "MERGED"
        assert decision.merged_into_node_id == existing_decision_id
        assert relation.to_node_id == decision.id  # immutable original endpoint
        assert action.parent_id == existing_decision_id
        assert action.graph_state == "ACTIVE"
        canonical_relations = list_canonical_relations(
            session, project_id=project
        )
        attached = next(
            row
            for row in canonical_relations
            if row.relation_id == relation.id
        )
        assert attached.canonical_to_node_id == existing_decision_id


def test_multiple_action_sources_merge_into_one_target(
    session_factory,
):
    project = "project-multi-source-action"
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="multi-source parent",
    )
    target_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=parent_id,
        title="multi-source action",
    )
    with session_factory() as session:
        before_version = session.get(Node, target_id).version

    result, _, _, action_candidate_ids = _run_multi_action_merge_scenario(
        session_factory,
        project=project,
        meeting="meeting-multi-source-action",
        decision_target_id=parent_id,
        action_target_id=target_id,
        action_inputs=[("item-2", 200), ("item-3", 300)],
    )

    assert len(result.merge_operation_ids) == 3
    with session_factory() as session:
        sources = session.execute(
            select(Node).where(Node.source_candidate_id.in_(action_candidate_ids))
        ).scalars().all()
        assert len(sources) == 2
        assert all(source.graph_state == "MERGED" for source in sources)
        assert all(source.merged_into_node_id == target_id for source in sources)
        target = session.get(Node, target_id)
        assert target.graph_state == "ACTIVE"
        assert target.parent_id == parent_id
        assert target.version == before_version + 2
        # The target was user-authored. Automatic merges may append Evidence,
        # but must not overwrite its protected title/content projection.
        assert target.title == "multi-source action"
        assert target.content == "multi-source action existing content"
        assert target.last_actor_type == "USER"
        assert session.execute(
            select(NodeEmbedding.status).where(NodeEmbedding.node_id == target_id)
        ).scalar_one() == "STALE"


@pytest.mark.parametrize("node_type", ["DECISION", "ISSUE"])
def test_non_action_same_target_multi_merge_absorbs_each_source_revision(
    session_factory,
    node_type,
):
    project = f"project-multi-source-{node_type.lower()}"
    meeting = f"meeting-multi-source-{node_type.lower()}"
    target_id = (
        _seed_existing_decision(
            session_factory,
            project=project,
            title="multi decision target",
        )
        if node_type == "DECISION"
        else _seed_existing_issue(
            session_factory,
            project=project,
            title="multi issue target",
        )
    )
    with session_factory() as session:
        before_version = session.get(Node, target_id).version
        before_revision_count = session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.node_id == target_id
            )
        )
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    candidate_ids = [
        _seed_candidate(
            session_factory,
            request_id=request_id,
            project=project,
            meeting=meeting,
            item_id=f"item-{index}",
            node_type=node_type,
            title=f"same {node_type.lower()} {index}",
            start_ms=index * 100,
        )
        for index in (1, 2)
    ]
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(value) for value in candidate_ids],
        embedding_client=TypeEmbedding(),
        b_model_client=SameTargetMergeB(target_id),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
    )

    assert len(result.merge_operation_ids) == 2
    with session_factory() as session:
        sources = list(
            session.execute(
                select(Node).where(
                    Node.source_candidate_id.in_(candidate_ids)
                )
            ).scalars()
        )
        assert all(source.graph_state == "MERGED" for source in sources)
        target = session.get(Node, target_id)
        assert target.version == before_version + 2
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.node_id == target_id
            )
        ) == before_revision_count + 2


def test_automatic_merge_does_not_mix_source_and_target_types(
    session_factory,
):
    project, meeting = (
        "project-multi-source-type-guard",
        "meeting-multi-source-type-guard",
    )
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="type guard parent",
    )
    action_target = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=parent_id,
        title="type guard action",
    )
    with session_factory() as session:
        session.get(
            NodeEmbedding,
            (action_target, EMBEDDING_CONTRACT_VERSION),
        ).embedding = [0.0, 0.0, 1.0] + [0.0] * 1533
        session.commit()
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    issue_candidate = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="ISSUE",
        title="issue must not merge into Action",
    )
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(issue_candidate)],
        embedding_client=TypeEmbedding(),
        b_model_client=SameTargetMergeB(action_target),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
    )

    assert result.merge_operation_ids == ()
    # The Action is a valid ISSUE parent candidate but never a valid ISSUE MERGE
    # target. A malicious B-model recommendation is rejected by the plan gate.
    assert "MERGE_TARGET_NOT_VALID_RETRIEVAL" in {
        warning["code"] for warning in result.warnings
    }


def test_action_merge_resolves_chained_decision_parent(session_factory):
    project = "project-action-parent-chain"
    decision_zero = _seed_existing_decision(
        session_factory,
        project=project,
        title="decision zero",
    )
    decision_one = _seed_existing_decision(
        session_factory,
        project=project,
        title="decision one",
    )
    action_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=decision_one,
        title="action with historical parent",
    )
    with session_factory() as session:
        decision_one_version = session.get(Node, decision_one).version
        decision_zero_version = session.get(Node, decision_zero).version
    user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=decision_one,
        target_node_id=decision_zero,
        source_expected_version=decision_one_version,
        target_expected_version=decision_zero_version,
        actor_id="seed",
        reason="historical canonical chain",
    )

    result, _, _, action_candidate_id = _run_action_merge_scenario(
        session_factory,
        project=project,
        meeting="meeting-action-parent-chain",
        decision_target_id=decision_zero,
        action_target_id=action_id,
    )

    assert len(result.merge_operation_ids) == 2
    assert "MERGE_ACTION_PARENT_CONFLICT" not in {
        warning["code"] for warning in result.warnings
    }
    with session_factory() as session:
        source = session.execute(
            select(Node).where(
                Node.source_candidate_id == action_candidate_id
            )
        ).scalar_one()
        assert source.graph_state == "MERGED"
        assert session.get(Node, action_id).parent_id == decision_one
        assert resolve_canonical_node(
            session,
            project_id=project,
            node_id=session.get(Node, action_id).parent_id,
        ).id == decision_zero


def test_action_merge_with_different_canonical_parent_is_downgraded(
    session_factory,
):
    project = "project-action-parent-conflict"
    intended_parent = _seed_existing_decision(
        session_factory,
        project=project,
        title="intended parent",
    )
    target_parent = _seed_existing_decision(
        session_factory,
        project=project,
        title="different target parent",
    )
    action_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=target_parent,
        title="action under another decision",
    )
    with session_factory() as session:
        session.get(NodeEmbedding, (target_parent, EMBEDDING_CONTRACT_VERSION)).status = "STALE"
        session.commit()

    result, _, _, action_candidate_id = _run_action_merge_scenario(
        session_factory,
        project=project,
        meeting="meeting-action-parent-conflict",
        decision_target_id=intended_parent,
        action_target_id=action_id,
    )

    assert "MERGE_ACTION_PARENT_CONFLICT" in {
        warning["code"] for warning in result.warnings
    }
    assert len(result.merge_operation_ids) == 1
    with session_factory() as session:
        source = session.execute(
            select(Node).where(
                Node.source_candidate_id == action_candidate_id
            )
        ).scalar_one()
        assert source.graph_state == "UNATTACHED"
        assert source.merged_into_node_id is None


def test_cross_project_action_parent_is_rejected_without_mutation(
    session_factory,
):
    other_parent = _seed_existing_decision(
        session_factory,
        project="project-other-parent",
        title="other project parent",
    )
    resolved = _resolve_existing_parent_canonical_id(
        session_factory,
        project_id="project-action-parent",
        category="BACKEND",
        parent_id=other_parent,
        missing_reason="MISSING",
        invalid_reason="INVALID",
    )
    assert resolved.canonical_id is None
    assert resolved.gate_reason == "INVALID"
    with session_factory() as session:
        other = session.get(Node, other_parent)
        assert other.project_id == "project-other-parent"
        assert other.graph_state == "ACTIVE"


def test_action_merge_plan_apply_is_idempotent(session_factory):
    project, meeting = (
        "project-action-idempotent",
        "meeting-action-idempotent",
    )
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="idempotent parent",
    )
    action_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=parent_id,
        title="idempotent action",
    )
    request_id = _seed_request(
        session_factory,
        project=project,
        meeting=meeting,
    )
    decision_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="idempotent decision candidate",
    )
    action_candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-2",
        node_type="ACTION",
        title="idempotent action candidate",
        parent_candidate_id=decision_candidate_id,
    )
    run_id = _seed_generation_run(
        session_factory,
        project=project,
        meeting=meeting,
    )
    source_request_id, candidates, warnings = (
        _source_request_and_candidates(
            session_factory,
            project_id=project,
            external_meeting_id=meeting,
            candidate_ids=[
                str(decision_candidate_id),
                str(action_candidate_id),
            ],
        )
    )
    assert warnings == []
    plan = build_graph_mutation_plan(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        source_request_id=source_request_id,
        candidates=candidates,
        embedding_client=TypeEmbedding(),
        b_model_client=DecisionAndActionMergeB(
            decision_target_id=parent_id,
            action_target_id=action_id,
        ),
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(
            min_similarity=0.9,
            min_margin=0.1,
        ),
        pipeline_label="automatic-b-model",
    )
    _set_run_stage(
        session_factory,
        run_id=run_id,
        project_id=project,
        status="VALIDATING",
    )
    first = apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )
    second = apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )
    assert first.replayed is False
    assert second.replayed is True
    with session_factory() as session:
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.node_id == action_id
            )
        ) == 2
        assert session.scalar(
            select(func.count(MergeOperation.id)).where(
                MergeOperation.generation_run_id == run_id
            )
        ) == 2
        assert session.scalar(
            select(func.count(Node.id)).where(
                Node.source_candidate_id.in_(
                    [decision_candidate_id, action_candidate_id]
                )
            )
        ) == 2
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.aggregate_id == str(run_id),
                OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED",
            )
        ) == 1


def test_multi_source_plan_replay_does_not_duplicate_group_artifacts(
    session_factory,
):
    project = "project-multi-source-idempotent"
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="multi idempotent parent",
    )
    target_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=parent_id,
        title="multi idempotent target",
    )
    plan, run_id, decision_candidate_id, action_candidate_ids = (
        _build_multi_action_merge_plan(
            session_factory,
            project=project,
            meeting="meeting-multi-source-idempotent",
            decision_target_id=parent_id,
            action_target_id=target_id,
            action_inputs=[
                ("item-2", 200),
                ("item-3", 300),
            ],
        )
    )
    _set_run_stage(
        session_factory,
        run_id=run_id,
        project_id=project,
        status="VALIDATING",
    )
    first = apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )
    second = apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )

    assert first.replayed is False
    assert second.replayed is True
    with session_factory() as session:
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.node_id == target_id
            )
        ) == 3
        assert session.scalar(
            select(func.count(MergeOperation.id)).where(
                MergeOperation.generation_run_id == run_id
            )
        ) == 3
        assert session.scalar(
            select(func.count(Node.id)).where(
                Node.source_candidate_id.in_(
                    [decision_candidate_id, *action_candidate_ids]
                )
            )
        ) == 3
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.aggregate_id == str(run_id),
                OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED",
            )
        ) == 1


def test_multi_source_partial_recovery_skips_already_merged_source(
    session_factory,
):
    project = "project-multi-source-partial-recovery"
    parent_id = _seed_existing_decision(
        session_factory,
        project=project,
        title="partial recovery parent",
    )
    target_id = _seed_existing_action(
        session_factory,
        project=project,
        parent_id=parent_id,
        title="partial recovery target",
    )
    plan, _, _, action_candidate_ids = _build_multi_action_merge_plan(
        session_factory,
        project=project,
        meeting="meeting-multi-source-partial-recovery",
        decision_target_id=parent_id,
        action_target_id=target_id,
        action_inputs=[
            ("item-2", 200),
            ("item-3", 300),
        ],
    )
    _set_run_stage(
        session_factory,
        run_id=plan.generation_run_id,
        project_id=project,
        status="VALIDATING",
    )
    apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=_settings(),
        pipeline_label="automatic-b-model",
    )
    with session_factory() as session:
        action_sources = {
            node.source_candidate_id: node
            for node in session.execute(
                select(Node).where(
                    Node.source_candidate_id.in_(action_candidate_ids)
                )
            ).scalars()
        }
        second_source = action_sources[action_candidate_ids[1]]
        second_operation = session.execute(
            select(MergeOperation).where(
                MergeOperation.source_node_id == second_source.id,
                MergeOperation.status == "APPLIED",
            )
        ).scalar_one()
    unmerge_operation(
        session_factory,
        project_id=project,
        operation_id=second_operation.id,
        actor_id="recovery-test",
    )

    with session_factory() as session:
        nodes_by_planned_id = {
            item.source.node_id: session.get(Node, item.source.node_id)
            for item in plan.items
        }
        locked_targets = {
            target_id: session.execute(
                select(Node)
                .where(
                    Node.id == target_id,
                    Node.project_id == project,
                )
                .with_for_update()
            ).scalar_one()
        }
        warnings: list[dict] = []
        recovered_operation_ids = (
            automatic_graph_module._apply_dependent_merge_groups(
                session,
                plan=plan,
                nodes_by_planned_id=nodes_by_planned_id,
                locked_targets=locked_targets,
                apply_warnings=warnings,
            )
        )
        session.commit()

    assert len(recovered_operation_ids) == 1
    assert warnings == []
    with session_factory() as session:
        sources = {
            node.source_candidate_id: node
            for node in session.execute(
                select(Node).where(
                    Node.source_candidate_id.in_(action_candidate_ids)
                )
            ).scalars()
        }
        assert all(node.graph_state == "MERGED" for node in sources.values())
        first_source_id = sources[action_candidate_ids[0]].id
        second_source_id = sources[action_candidate_ids[1]].id
        assert session.scalar(
            select(func.count(MergeOperation.id)).where(
                MergeOperation.source_node_id == first_source_id,
                MergeOperation.status == "APPLIED",
            )
        ) == 1
        assert session.scalar(
            select(func.count(MergeOperation.id)).where(
                MergeOperation.source_node_id == second_source_id,
                MergeOperation.status == "APPLIED",
            )
        ) == 1
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.node_id == target_id
            )
        ) == 4


def test_logical_merge_unmerge_keeps_target_user_edit(session_factory):
    project = "project-unmerge"
    source = _seed_existing_decision(
        session_factory, project=project, title="source"
    )
    target = _seed_existing_decision(
        session_factory, project=project, title="target"
    )
    with session_factory() as session:
        source_version = session.get(Node, source).version
        target_version = session.get(Node, target).version
        source_revision_id = session.get(Node, source).current_revision_id
        source_evidence_count = session.scalar(
            select(func.count(NodeRevisionEvidence.evidence_id)).where(
                NodeRevisionEvidence.node_revision_id == source_revision_id
            )
        )
    merged = user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=source,
        target_node_id=target,
        source_expected_version=source_version,
        target_expected_version=target_version,
        actor_id="user-1",
        reason="same decision",
    )
    with session_factory() as session:
        target_node = session.get(Node, target)
        target_version = target_node.version
    edit_node(
        session_factory,
        project_id=project,
        node_id=target,
        actor_id="user-2",
        request_id="edit-after-merge",
        expected_version=target_version,
        title="target edited after merge",
    )
    unmerge_operation(
        session_factory,
        project_id=project,
        operation_id=merged.operation_id,
        actor_id="user-1",
    )
    with session_factory() as session:
        source_node = session.get(Node, source)
        target_node = session.get(Node, target)
        operation = session.get(MergeOperation, merged.operation_id)
        assert source_node.graph_state == "ACTIVE"
        assert source_node.merged_into_node_id is None
        assert source_node.current_revision_id == source_revision_id
        assert session.scalar(
            select(func.count(NodeRevisionEvidence.evidence_id)).where(
                NodeRevisionEvidence.node_revision_id == source_revision_id
            )
        ) == source_evidence_count
        assert target_node.title == "target edited after merge"
        assert operation.status == "REVERTED"


def test_merge_rejects_self_type_mismatch_and_cycle(session_factory):
    project = "project-merge-guards"
    first = _seed_existing_decision(
        session_factory, project=project, title="first"
    )
    second = _seed_existing_decision(
        session_factory, project=project, title="second"
    )
    action = create_user_node(
        session_factory,
        project_id=project,
        actor_id="seed",
        request_id="seed-action",
        node_type="ACTION",
        category="BACKEND",
        title="action",
        content="action",
        due_date=None,
        evidence_assertion="action assertion",
        external_meeting_id=None,
    ).node_id
    with session_factory() as session:
        versions = {
            node_id: session.get(Node, node_id).version
            for node_id in (first, second, action)
        }
    with pytest.raises(GraphMutationValidationError, match="itself"):
        user_merge_nodes(
            session_factory,
            project_id=project,
            source_node_id=first,
            target_node_id=first,
            source_expected_version=versions[first],
            target_expected_version=versions[first],
            actor_id="user",
            reason="invalid self merge",
        )
    with pytest.raises(GraphMutationValidationError, match="same type"):
        user_merge_nodes(
            session_factory,
            project_id=project,
            source_node_id=action,
            target_node_id=first,
            source_expected_version=versions[action],
            target_expected_version=versions[first],
            actor_id="user",
            reason="invalid type merge",
        )
    first_merge = user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=first,
        target_node_id=second,
        source_expected_version=versions[first],
        target_expected_version=versions[second],
        actor_id="user",
        reason="first into second",
    )
    with session_factory() as session:
        second_version = session.get(Node, second).version
        first_version = session.get(Node, first).version
    with pytest.raises(GraphMutationValidationError, match="cycle"):
        user_merge_nodes(
            session_factory,
            project_id=project,
            source_node_id=second,
            target_node_id=first,
            source_expected_version=second_version,
            target_expected_version=first_version,
            actor_id="user",
            reason="must not cycle",
        )
    assert first_merge.operation_id is not None


def test_project_isolation_blocks_user_merge(session_factory):
    source = _seed_existing_decision(
        session_factory, project="project-a", title="source"
    )
    target = _seed_existing_decision(
        session_factory, project="project-b", title="target"
    )
    with session_factory() as session:
        source_version = session.get(Node, source).version
        target_version = session.get(Node, target).version
    with pytest.raises(Exception, match="cross project|missing"):
        user_merge_nodes(
            session_factory,
            project_id="project-a",
            source_node_id=source,
            target_node_id=target,
            source_expected_version=source_version,
            target_expected_version=target_version,
            actor_id="user",
            reason="must fail",
        )
    with session_factory() as session:
        assert session.get(Node, source).graph_state == "ACTIVE"
        assert session.get(Node, target).graph_state == "ACTIVE"


def test_user_relation_rejects_a_cross_category_parent(session_factory):
    project = "project-relation-category-boundary"
    parent = _seed_existing_decision(
        session_factory,
        project=project,
        title="infra parent",
    )
    child = create_user_node(
        session_factory,
        project_id=project,
        actor_id="tester",
        request_id="cross-category-child",
        node_type="ACTION",
        category="BACKEND",
        title="backend child",
        content="backend child content",
        due_date=None,
        evidence_assertion="backend child evidence",
        external_meeting_id=None,
    ).node_id
    with session_factory() as session:
        session.get(Node, parent).category = "INFRA"
        child_version = session.get(Node, child).version
        parent_version = session.get(Node, parent).version
        session.commit()

    with pytest.raises(GraphMutationValidationError):
        create_relation(
            session_factory,
            project_id=project,
            actor_id="tester",
            from_node_id=child,
            to_node_id=parent,
            relation_type="ATTACHED_TO",
            from_expected_version=child_version,
            to_expected_version=parent_version,
        )

    with session_factory() as session:
        assert session.get(Node, child).parent_id is None
        assert session.query(Relation).count() == 0


def test_sqs_facing_automatic_runner_completes_empty_fake_meeting(
    session_factory,
):
    result = run_automatic_meeting(
        session_factory,
        meeting_input={
            "requestId": "s3-" + "a" * 64,
            "recordingHash": "a" * 64,
            "projectId": "project-empty",
            "externalMeetingId": "meeting-empty",
            "segments": [],
        },
        client=FakeMeetingChatClient("meeting-empty"),
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    assert result.proposal_result.status == "COMPLETED"
    with session_factory() as session:
        run = session.execute(select(GenerationRun)).scalar_one()
        assert run.status == "COMPLETED"
        assert run.result_summary["createdCount"] == 0


def test_summary_failure_after_graph_commit_emits_compensating_failed_state(
    session_factory,
):
    class FailingSummary:
        name = "failing-fixture"
        version = "v1"

        def generate(self, request):
            del request
            raise RuntimeError("provider payload must not leak")

    with pytest.raises(RuntimeError, match="provider payload"):
        run_automatic_meeting(
            session_factory,
            meeting_input={
                "requestId": "s3-" + "e" * 64,
                "recordingHash": "e" * 64,
                "projectId": "project-summary-failure",
                "externalMeetingId": "meeting-summary-failure",
                "segments": [],
            },
            client=FakeMeetingChatClient("meeting-summary-failure"),
            embedding_client=UnitEmbedding(),
            b_model_client=CreateOnlyB(),
            retrieval_settings=_settings(),
            meeting_summary_generator=FailingSummary(),
            generate_summary=True,
        )
    with session_factory() as session:
        run = session.execute(select(GenerationRun)).scalar_one()
        assert run.status == "COMPLETED"
        state = session.execute(select(AnalysisDeliveryState)).scalar_one()
        assert state.status == "FAILED"
        assert state.failure_code == "AUTOMATIC_GRAPH_FAILED"
        event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_STATUS_CHANGED",
                OutboxEvent.payload["status"].as_string() == "FAILED",
            )
        ).scalar_one()
        assert event.payload["failureMessage"] == "RuntimeError"
        assert "provider payload" not in str(event.payload)


def test_automatic_runner_replay_does_not_duplicate_graph_or_outbox(
    session_factory,
):
    meeting_input = {
        "requestId": "s3-" + "b" * 64,
        "recordingHash": "b" * 64,
        "projectId": "project-replay",
        "externalMeetingId": "meeting-replay",
        "segments": [],
    }
    first = run_automatic_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=FakeMeetingChatClient("meeting-replay"),
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    second = run_automatic_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=FakeMeetingChatClient("meeting-replay"),
        embedding_client=UnitEmbedding(),
        b_model_client=CreateOnlyB(),
        retrieval_settings=_settings(),
    )
    assert first.proposal_result.status == "COMPLETED"
    assert second.proposal_result.outcome == "AUTOMATIC_GRAPH_REPLAYED"
    with session_factory() as session:
        assert session.scalar(select(func.count(GenerationRun.id))) == 1
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED"
            )
        ) == 1


def test_apply_failure_rolls_back_all_graph_rows(session_factory, monkeypatch):
    project, meeting = "project-atomic", "meeting-atomic"
    request_id = _seed_request(
        session_factory, project=project, meeting=meeting
    )
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="원자성 검증",
    )
    run_id = _seed_generation_run(
        session_factory, project=project, meeting=meeting
    )

    def fail_after_graph_rows(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("forced trace persistence failure")

    monkeypatch.setattr(
        "data_pipeline.pipeline.automatic_graph._persist_analysis_trace",
        fail_after_graph_rows,
    )
    with pytest.raises(RuntimeError, match="forced trace"):
        run_automatic_graph(
            session_factory,
            generation_run_id=run_id,
            project_id=project,
            external_meeting_id=meeting,
            candidate_ids=[str(candidate_id)],
            embedding_client=UnitEmbedding(),
            b_model_client=CreateOnlyB(),
            retrieval_settings=_settings(),
        )
    with session_factory() as session:
        assert session.scalar(
            select(func.count(Node.id)).where(Node.project_id == project)
        ) == 0
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(
                NodeRevision.project_id == project
            )
        ) == 0
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.aggregate_id == str(run_id),
                OutboxEvent.event_type == "GRAPH_GENERATION_COMPLETED",
            )
        ) == 0
        assert session.get(GenerationRun, run_id).status == "VALIDATING"


def test_sqs_facing_failure_is_durable_and_not_partially_published(
    session_factory,
):
    def failed_meeting_runner(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("A model unavailable")

    with pytest.raises(RuntimeError, match="A model unavailable"):
        run_automatic_meeting(
            session_factory,
            meeting_input={
                "requestId": "s3-" + "f" * 64,
                "recordingHash": "f" * 64,
                "projectId": "project-failed",
                "externalMeetingId": "meeting-failed",
                "segments": [],
            },
            client=FakeMeetingChatClient("meeting-failed"),
            embedding_client=UnitEmbedding(),
            b_model_client=CreateOnlyB(),
            retrieval_settings=_settings(),
            meeting_runner=failed_meeting_runner,
        )
    with session_factory() as session:
        run = session.execute(
            select(GenerationRun).where(
                GenerationRun.project_id == "project-failed"
            )
        ).scalar_one()
        assert run.status == "FAILED"
        assert session.scalar(
            select(func.count(Node.id)).where(
                Node.project_id == "project-failed"
            )
        ) == 0
        failed_event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == str(run.id),
                OutboxEvent.event_type == "GRAPH_GENERATION_FAILED",
            )
        ).scalar_one()
        assert failed_event.payload["errorType"] == "RuntimeError"


def test_chain_unmerge_requires_reverse_operation_order(session_factory):
    project = "project-chain"
    first = _seed_existing_decision(
        session_factory, project=project, title="first"
    )
    second = _seed_existing_decision(
        session_factory, project=project, title="second"
    )
    third = _seed_existing_decision(
        session_factory, project=project, title="third"
    )
    related = create_user_node(
        session_factory,
        project_id=project,
        actor_id="seed",
        request_id="seed-related-action",
        node_type="ACTION",
        category="BACKEND",
        title="related action",
        content="related action",
        due_date=None,
        evidence_assertion="related action assertion",
        external_meeting_id=None,
    ).node_id
    with session_factory() as session:
        versions = {
            node_id: session.get(Node, node_id).version
            for node_id in (first, second, third, related)
        }
    relation = create_relation(
        session_factory,
        project_id=project,
        actor_id="user",
        from_node_id=related,
        to_node_id=first,
        relation_type="ATTACHED_TO",
        from_expected_version=versions[related],
        to_expected_version=versions[first],
    )
    op1 = user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=first,
        target_node_id=second,
        source_expected_version=versions[first],
        target_expected_version=versions[second],
        actor_id="user",
        reason="first into second",
    )
    op2 = user_merge_nodes(
        session_factory,
        project_id=project,
        source_node_id=second,
        target_node_id=third,
        source_expected_version=versions[second],
        target_expected_version=versions[third],
        actor_id="user",
        reason="second into third",
    )
    with session_factory() as session:
        assert resolve_canonical_node(
            session, project_id=project, node_id=first
        ).id == third
        current_relation = next(
            row
            for row in list_canonical_relations(
                session, project_id=project
            )
            if str(row.relation_id) == relation.relationId
        )
        assert current_relation.original_to_node_id == first
        assert current_relation.canonical_to_node_id == third
    with pytest.raises(MergeNotReversibleError):
        unmerge_operation(
            session_factory,
            project_id=project,
            operation_id=op1.operation_id,
            actor_id="user",
        )
    unmerge_operation(
        session_factory,
        project_id=project,
        operation_id=op2.operation_id,
        actor_id="user",
    )
    with session_factory() as session:
        assert resolve_canonical_node(
            session, project_id=project, node_id=first
        ).id == second
    unmerge_operation(
        session_factory,
        project_id=project,
        operation_id=op1.operation_id,
        actor_id="user",
    )
    with session_factory() as session:
        assert session.get(Node, first).graph_state == "ACTIVE"
        assert session.get(Node, second).graph_state == "ACTIVE"
        assert session.get(Node, third).graph_state == "ACTIVE"
        restored_relation = next(
            row
            for row in list_canonical_relations(
                session, project_id=project
            )
            if str(row.relation_id) == relation.relationId
        )
        assert restored_relation.original_to_node_id == first
        assert restored_relation.canonical_to_node_id == first


def test_postgresql_rejects_evidenceless_required_revision(session_factory):
    with session_factory() as probe:
        if probe.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL deferred constraint trigger")
    node_id = _seed_existing_decision(
        session_factory,
        project="project-trigger",
        title="trigger node",
    )
    with session_factory() as session:
        node = session.get(Node, node_id)
        session.add(
            NodeRevision(
                project_id=node.project_id,
                node_id=node.id,
                version=node.version + 1,
                title="must fail",
                content=node.content,
                node_type=node.node_type,
                category=node.category,
                created_by_type="USER",
                requires_evidence=True,
            )
        )
        with pytest.raises(DBAPIError, match="requires at least one evidence"):
            session.commit()
