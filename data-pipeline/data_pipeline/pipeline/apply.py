"""규칙 8·9 실행 — Change Plan 을 PG 에 원자 적용.

- Plan 단위 원자성: 여기서 예외가 나면 호출자(service)가 트랜잭션을 롤백 → 부분 성공 없음.
- 순차 적용: 정렬 키 순서로 적용하되, 같은 회의 안의 부모(itemId)가 자식보다 먼저 생성되도록
  위상 정렬로 보정한다(부모-자식 무결성). UPDATE/MINUTES 는 정렬 키 순서를 유지.
- optimistic lock(규칙 9): UPDATE 는 조건부 UPDATE(WHERE version=expected)로 lost update 를 막고,
  rowcount=0 이면 StaleVersionError → 전체 롤백(STALE).
- change_event(append-only)·outbox_event 도 같은 트랜잭션에서 기록.
"""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from data_pipeline.contracts import (
    ApplyResult,
    CategorySet,
    ChangePlan,
    Command,
    CreatedNode,
    MinutesOnlyEntry,
    NodeType,
    PlanOp,
    UpdatedNode,
    default_lifecycle_status,
    parent_rule_violation,
    transition_allowed,
)
from data_pipeline.contracts.change_plan import CREATE_OPS
from data_pipeline.contracts.enums import GraphState
from data_pipeline.storage.models import GraphChangeEvent, Node, OutboxEvent
from data_pipeline.storage.evidence import upsert_node_evidence
from data_pipeline.validation.normalize import normalize_quote

from .errors import ApplyError, StaleVersionError
from .repository import get_node


def _snapshot(node: Node) -> dict:
    return {
        "nodeId": str(node.id),
        "nodeType": node.node_type,
        "category": node.category,
        "title": node.title,
        "parentId": str(node.parent_id) if node.parent_id else None,
        "graphState": node.graph_state,
        "lifecycleStatus": node.lifecycle_status,
        "version": node.version,
        "dueDate": node.due_date,
    }


def _ordered_for_apply(commands: list[Command]) -> list[Command]:
    """정렬 키 순서 + 같은 회의 부모(itemId) 선행 보장 (위상 정렬). 순환 시 ApplyError."""
    by_item_create = {c.itemId: c for c in commands if c.op.value in CREATE_OPS}
    emitted: set[str] = set()
    remaining = list(commands)
    ordered: list[Command] = []

    def ready(cmd: Command) -> bool:
        parent = cmd.parent
        if parent and parent.newParentItemId:
            ref = parent.newParentItemId
            if ref in by_item_create and ref not in emitted:
                return False
        return True

    while remaining:
        candidates = [c for c in remaining if ready(c)]
        if not candidates:
            raise ApplyError("Change Plan 부모 참조가 순환합니다 (attachTo cycle)")
        chosen = min(candidates, key=lambda c: c.sortKey.as_tuple())
        ordered.append(chosen)
        emitted.add(chosen.itemId)
        remaining.remove(chosen)
    return ordered


def _resolve_parent(
    session: Session, cmd: Command, item_node: dict[str, tuple[str, str]]
) -> tuple[str | None, str | None]:
    """(parent_id, parent_type) 반환. root 면 (None, None)."""
    parent = cmd.parent
    if parent is None or parent.is_root():
        return None, None
    if parent.newParentItemId:
        ref = item_node.get(parent.newParentItemId)
        if ref is None:
            raise ApplyError(f"부모 itemId {parent.newParentItemId!r} 가 이 Plan 에서 생성되지 않았습니다")
        return ref[0], ref[1]
    node = get_node(session, parent.existingNodeId)
    if node is None:
        raise ApplyError(f"기존 부모 노드 {parent.existingNodeId!r} 를 찾을 수 없습니다")
    return str(node.id), node.node_type


def _find_duplicate(
    session: Session, project_id: str, meeting_id: str, cmd: Command
) -> Node | None:
    """규칙 7: (project, meeting, item) 자연키 또는 동일 제목·근거 노드 사전 감지."""
    from sqlalchemy import select

    natural = session.execute(
        select(Node).where(
            Node.project_id == project_id,
            Node.source_meeting_id == meeting_id,
            Node.source_item_id == cmd.itemId,
        )
    ).scalar_one_or_none()
    if natural is not None:
        return natural

    seg_ids = tuple(sorted({ev.segmentId for ev in cmd.evidence}))
    norm_title = normalize_quote(cmd.title or "")
    for node in session.execute(select(Node).where(Node.project_id == project_id)).scalars():
        node_segs = tuple(sorted({ev.segment_id for ev in node.evidence}))
        if normalize_quote(node.title or "") == norm_title and node_segs == seg_ids and seg_ids:
            return node
    return None


def apply_change_plan(session: Session, plan: ChangePlan, category_set: CategorySet) -> ApplyResult:
    project_id = plan.projectId
    meeting_id = plan.externalMeetingId
    request_id = plan.requestId

    created: list[CreatedNode] = []
    updated: list[UpdatedNode] = []
    minutes: list[MinutesOnlyEntry] = []
    applied_order: list[str] = []
    skipped_dupes: list[dict] = []
    item_node: dict[str, tuple[str, str]] = {}  # itemId -> (node_uuid, node_type)

    for cmd in _ordered_for_apply(plan.commands):
        applied_order.append(cmd.itemId)

        if cmd.op.value in CREATE_OPS:
            ntype = cmd.nodeType.value
            graph_state = cmd.graphState.value
            parent_id, parent_type = _resolve_parent(session, cmd, item_node)
            violation = parent_rule_violation(ntype, parent_type, graph_state)
            if violation:
                raise ApplyError(f"부모 규칙 위반({cmd.itemId}): {violation}")
            if not category_set.is_valid(cmd.category):
                raise ApplyError(f"알 수 없는 카테고리 {cmd.category!r} ({cmd.itemId})")

            dup = _find_duplicate(session, project_id, meeting_id, cmd)
            if dup is not None:
                item_node[cmd.itemId] = (str(dup.id), dup.node_type)
                skipped_dupes.append({"itemId": cmd.itemId, "existingNodeId": str(dup.id)})
                continue

            node = Node(
                project_id=project_id,
                source_meeting_id=meeting_id,
                source_item_id=cmd.itemId,
                node_type=ntype,
                category=cmd.category,
                title=cmd.title or "",
                content=cmd.content or "",
                parent_id=uuid.UUID(parent_id) if parent_id else None,
                graph_state=graph_state,
                lifecycle_status=default_lifecycle_status(ntype),
            )
            session.add(node)
            session.flush()
            for ev in cmd.evidence:
                upsert_node_evidence(
                    session,
                    node_id=node.id,
                    segment_id=ev.segmentId,
                    quote=ev.quote,
                    quote_start=ev.quoteStart,
                    quote_end=ev.quoteEnd,
                    evidence_type="MEETING",
                    source_meeting_id=meeting_id,
                )
            item_node[cmd.itemId] = (str(node.id), ntype)
            created.append(CreatedNode(
                itemId=cmd.itemId, nodeId=str(node.id), nodeType=NodeType(ntype),
                parentId=parent_id,
            ))
            session.add(GraphChangeEvent(
                project_id=project_id, request_id=request_id, node_id=node.id, item_id=cmd.itemId,
                change_type="CREATE", actor_type="AI", before=None, after=_snapshot(node),
            ))

        elif cmd.op == PlanOp.UPDATE_ACTION:
            node = get_node(session, cmd.targetActionId)
            if node is None:
                raise ApplyError(f"UPDATE 대상 노드 {cmd.targetActionId!r} 를 찾을 수 없습니다")
            if node.node_type != NodeType.ACTION.value:
                raise ApplyError(f"UPDATE 대상이 ACTION 이 아님: {cmd.targetActionId!r}")
            before = _snapshot(node)
            expected = cmd.expectedVersion
            changes = cmd.changes or {}
            new_status = changes.get("status")
            if new_status and not transition_allowed(NodeType.ACTION.value, node.lifecycle_status, new_status):
                raise ApplyError(f"허용되지 않는 전이({cmd.targetActionId}): {node.lifecycle_status}->{new_status}")

            new_version = (expected if expected is not None else node.version) + 1
            values: dict = {"version": new_version}
            if new_status:
                values["lifecycle_status"] = new_status
            if "dueDate" in changes:
                values["due_date"] = changes["dueDate"]

            where_version = expected if expected is not None else node.version
            result = session.execute(
                update(Node).where(Node.id == node.id, Node.version == where_version).values(**values)
            )
            if result.rowcount == 0:  # 규칙 9: version 불일치 → STALE
                session.expire(node)
                actual = get_node(session, cmd.targetActionId)
                raise StaleVersionError(cmd.targetActionId, expected, actual.version if actual else None)
            session.expire(node)
            after = _snapshot(get_node(session, cmd.targetActionId))
            updated.append(UpdatedNode(
                itemId=cmd.itemId, nodeId=str(node.id), changes={k: str(v) for k, v in changes.items()},
                fromVersion=before["version"], toVersion=new_version,
            ))
            session.add(GraphChangeEvent(
                project_id=project_id, request_id=request_id, node_id=node.id, item_id=cmd.itemId,
                change_type="UPDATE", actor_type="AI", before=before, after=after,
            ))

        else:  # RECORD_MINUTES
            minutes.append(MinutesOnlyEntry(itemId=cmd.itemId, reason=cmd.reason or "NO_RELATED_DECISION"))
            session.add(GraphChangeEvent(
                project_id=project_id, request_id=request_id, node_id=None, item_id=cmd.itemId,
                change_type="MINUTES_ONLY", actor_type="AI",
                before=None, after=None, detail={"reason": cmd.reason},
            ))

    result = ApplyResult(
        requestId=request_id,
        externalMeetingId=meeting_id,
        status="COMPLETED",
        createdNodes=created,
        updatedNodes=updated,
        minutesOnly=minutes,
        detail={"appliedOrder": applied_order, "skippedDuplicates": skipped_dupes},
    )
    # 범용 outbox 이벤트 (스프링 연동은 M4 — 여기서는 발행만).
    session.add(OutboxEvent(
        event_type="MEETING_PROCESSING_COMPLETED",
        aggregate_type="meeting_request",
        aggregate_id=request_id,
        project_id=project_id,
        payload={
            "requestId": request_id,
            "externalMeetingId": meeting_id,
            "created": [c.model_dump(mode="json") for c in created],
            "updated": [u.model_dump(mode="json") for u in updated],
            "minutesOnly": [m.model_dump(mode="json") for m in minutes],
        },
    ))
    return result
