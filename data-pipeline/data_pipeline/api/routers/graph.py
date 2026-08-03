"""Automatic graph reads and user post-edit mutations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data_pipeline.api.dependencies import (
    get_actor_id,
    get_project_id,
    get_request_id,
    get_session_factory,
)
from data_pipeline.api.graph_services import (
    create_relation,
    delete_relation,
    get_generation_run_view,
    get_graph_node_view,
    get_project_graph_snapshot,
    list_graph_nodes,
    replace_relation,
)
from data_pipeline.api.schemas import (
    GenerationRunView,
    GraphMutationResponse,
    GraphNodeListResponse,
    GraphNodePatchRequest,
    GraphNodeView,
    Identifier,
    LogicalMergeRequest,
    NodeDeleteRequest,
    RelationCreateRequest,
    RelationReplaceRequest,
    RelationView,
    UserNodeCreateRequest,
)
from data_pipeline.pipeline.graph import unmerge_operation
from data_pipeline.pipeline.user_graph import (
    create_user_node,
    delete_node,
    edit_node,
    remerge_operation,
    user_merge_nodes,
)

router = APIRouter(prefix="/api/v1", tags=["graph"])
internal_router = APIRouter(prefix="/internal", tags=["internal-graph"])


@internal_router.get("/projects/{project_id}/graph-snapshot")
def graph_snapshot(
    project_id: str,
    session_factory=Depends(get_session_factory),
) -> dict:
    snapshot = get_project_graph_snapshot(
        session_factory,
        project_id=project_id,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project graph not found",
        )
    return snapshot


@router.get("/generation-runs/{run_id}", response_model=GenerationRunView)
def generation_run(
    run_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> GenerationRunView:
    return get_generation_run_view(
        session_factory,
        project_id=project_id,
        run_id=run_id,
    )


@router.get("/nodes", response_model=GraphNodeListResponse)
def nodes(
    graph_state: str = Query(
        default="ACTIVE,UNATTACHED",
        alias="graphState",
    ),
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> GraphNodeListResponse:
    states = {
        value.strip().upper()
        for value in graph_state.split(",")
        if value.strip()
    }
    return list_graph_nodes(
        session_factory,
        project_id=project_id,
        graph_states=states,
    )


@router.get("/nodes/{node_id}", response_model=GraphNodeView)
def node(
    node_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> GraphNodeView:
    return get_graph_node_view(
        session_factory,
        project_id=project_id,
        node_id=node_id,
    )


@router.patch("/nodes/{node_id}", response_model=GraphMutationResponse)
def patch_node(
    node_id: Identifier,
    payload: GraphNodePatchRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    request_id: str | None = Depends(get_request_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    result = edit_node(
        session_factory,
        project_id=project_id,
        node_id=node_id,
        actor_id=actor_id,
        request_id=request_id,
        expected_version=payload.expectedVersion,
        title=payload.title,
        content=payload.content,
        node_type=payload.nodeType,
        category=payload.category,
        due_date=payload.dueDate,
        evidence_assertion=payload.evidenceAssertion,
        new_parent_node_id=payload.newParentNodeId,
    )
    return GraphMutationResponse(
        nodeId=str(result.node_id),
        version=result.version,
        graphState=result.graph_state,
        operationId=None,
        relationId=None,
        changed=result.changed,
    )


@router.post("/nodes", response_model=GraphMutationResponse)
def post_node(
    payload: UserNodeCreateRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    request_id: str | None = Depends(get_request_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    result = create_user_node(
        session_factory,
        project_id=project_id,
        actor_id=actor_id,
        request_id=request_id,
        node_type=payload.nodeType,
        category=payload.category,
        title=payload.title,
        content=payload.content,
        due_date=payload.dueDate,
        evidence_assertion=payload.evidenceAssertion,
        external_meeting_id=payload.externalMeetingId,
    )
    return GraphMutationResponse(
        nodeId=str(result.node_id),
        version=result.version,
        graphState=result.graph_state,
        changed=result.changed,
    )


@router.delete("/nodes/{node_id}", response_model=GraphMutationResponse)
def remove_node(
    node_id: Identifier,
    payload: NodeDeleteRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    request_id: str | None = Depends(get_request_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    result = delete_node(
        session_factory,
        project_id=project_id,
        node_id=node_id,
        actor_id=actor_id,
        request_id=request_id,
        expected_version=payload.expectedVersion,
    )
    return GraphMutationResponse(
        nodeId=str(result.node_id),
        version=result.version,
        graphState=result.graph_state,
        changed=result.changed,
    )


@router.post("/nodes/{source_id}/merge", response_model=GraphMutationResponse)
def merge_node(
    source_id: Identifier,
    payload: LogicalMergeRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    result = user_merge_nodes(
        session_factory,
        project_id=project_id,
        source_node_id=source_id,
        target_node_id=payload.targetNodeId,
        source_expected_version=payload.sourceExpectedVersion,
        target_expected_version=payload.targetExpectedVersion,
        actor_id=actor_id,
        reason=payload.reason,
    )
    return GraphMutationResponse(
        nodeId=str(result.node_id),
        version=result.version,
        graphState=result.graph_state,
        operationId=str(result.operation_id),
        changed=result.changed,
    )


@router.post(
    "/merge-operations/{operation_id}/unmerge",
    response_model=GraphMutationResponse,
)
def unmerge(
    operation_id: Identifier,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    operation = unmerge_operation(
        session_factory,
        project_id=project_id,
        operation_id=operation_id,
        actor_id=actor_id,
    )
    view = get_graph_node_view(
        session_factory,
        project_id=project_id,
        node_id=operation.source_node_id,
    )
    return GraphMutationResponse(
        nodeId=view.nodeId,
        version=view.version,
        graphState=view.graphState,
        operationId=str(operation.id),
        changed=True,
    )


@router.post(
    "/merge-operations/{operation_id}/remerge",
    response_model=GraphMutationResponse,
)
def remerge(
    operation_id: Identifier,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> GraphMutationResponse:
    result = remerge_operation(
        session_factory,
        project_id=project_id,
        operation_id=operation_id,
        actor_id=actor_id,
    )
    return GraphMutationResponse(
        nodeId=str(result.node_id),
        version=result.version,
        graphState=result.graph_state,
        operationId=str(result.operation_id),
        changed=result.changed,
    )


@router.post("/relations", response_model=RelationView)
def post_relation(
    payload: RelationCreateRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> RelationView:
    return create_relation(
        session_factory,
        project_id=project_id,
        actor_id=actor_id,
        from_node_id=payload.fromNodeId,
        to_node_id=payload.toNodeId,
        relation_type=payload.relationType,
        from_expected_version=payload.fromExpectedVersion,
        to_expected_version=payload.toExpectedVersion,
    )


@router.patch("/relations/{relation_id}", response_model=RelationView)
def patch_relation(
    relation_id: Identifier,
    payload: RelationReplaceRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> RelationView:
    return replace_relation(
        session_factory,
        project_id=project_id,
        actor_id=actor_id,
        relation_id=relation_id,
        to_node_id=payload.toNodeId,
        relation_type=payload.relationType,
        from_expected_version=payload.fromExpectedVersion,
        to_expected_version=payload.toExpectedVersion,
    )


@router.delete("/relations/{relation_id}", response_model=RelationView)
def remove_relation(
    relation_id: Identifier,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> RelationView:
    return delete_relation(
        session_factory,
        project_id=project_id,
        actor_id=actor_id,
        relation_id=relation_id,
    )


__all__ = ["internal_router", "router"]
