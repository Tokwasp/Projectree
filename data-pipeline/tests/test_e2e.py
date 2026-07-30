"""가짜 JSON E2E (M1 인수 기준).

시나리오: 정상 경로 / 멱등성 / 상태 세탁 강등 / 순차 적용 / optimistic lock / 원자성 롤백
+ PoC 우회 입력(itemId 중복, "네" quote, 후보 밖 ID).
"""

from __future__ import annotations

import copy
import types
import uuid

import pytest

from data_pipeline.contracts import (
    CategorySet,
    ChangePlan,
    Command,
    EvidenceRef,
    Lineage,
    NodeType,
    ParentRef,
    PlanOp,
    SortKey,
)
from data_pipeline.pipeline import (
    ApplyError,
    StaleVersionError,
    apply_change_plan,
    process_request,
    seed_node,
)
from data_pipeline.storage import (
    GraphChangeEvent,
    Node,
    NodeEvidence,
    OutboxEvent,
    Request,
    TranscriptSegment,
    session_scope,
)

from .support import (
    PROJECT,
    count,
    ev,
    item,
    judgment,
    load_fixture,
    request_payload,
    seg,
)

CS = CategorySet.load()


@pytest.fixture(autouse=True)
def _enable_quarantined_legacy_apply_tests(monkeypatch):
    monkeypatch.setenv(
        "DATA_PIPELINE_UNSAFE_ENABLE_LEGACY_GRAPH_MUTATION_FOR_TESTS",
        "1",
    )


def _nodes(session_factory):
    with session_factory() as s:
        return {n.source_item_id: n for n in s.query(Node).all()}


# --- 1. 정상 경로 ------------------------------------------------------------
def test_normal_path_creates_graph_and_events(session_factory):
    res = process_request(session_factory, load_fixture("normal_create.json"))
    assert res.status == "COMPLETED"
    assert {c.itemId for c in res.createdNodes} == {"m1", "m2", "m3"}
    assert count(session_factory, Node) == 3
    assert count(session_factory, OutboxEvent) == 1

    with session_factory() as s:
        creates = s.query(GraphChangeEvent).filter_by(change_type="CREATE").count()
        assert creates == 3
        by_item = {n.source_item_id: n for n in s.query(Node).all()}
        # 부모 배선: m2(ACTION)->m1(DECISION), m3(ISSUE)->m2(ACTION)
        assert by_item["m1"].parent_id is None
        assert by_item["m2"].parent_id == by_item["m1"].id
        assert by_item["m3"].parent_id == by_item["m2"].id
        assert by_item["m1"].lifecycle_status == "ACTIVE"
        assert by_item["m2"].lifecycle_status == "TODO"
        assert by_item["m3"].lifecycle_status == "OPEN"

        # v2.2 스키마 충실도: outbox 이벤트 타입, evidence 오프셋 역산, 세그먼트 sequence_no/hash.
        outbox = s.query(OutboxEvent).one()
        assert outbox.event_type == "MEETING_PROCESSING_COMPLETED"
        m1_ev = s.query(NodeEvidence).filter_by(node_id=by_item["m1"].id).one()
        assert m1_ev.quote_start == 0 and m1_ev.quote_end is not None  # 서버 역산 오프셋
        assert m1_ev.source_meeting_id == "M-NORMAL"
        segs = s.query(TranscriptSegment).filter_by(external_meeting_id="M-NORMAL").all()
        assert sorted(x.sequence_no for x in segs) == [0, 1, 2]
        assert all(x.text_hash for x in segs)


# --- 2. 멱등성 ---------------------------------------------------------------
def test_idempotency_duplicate_and_reject(session_factory):
    payload = load_fixture("normal_create.json")
    assert process_request(session_factory, payload).status == "COMPLETED"

    dup = process_request(session_factory, copy.deepcopy(payload))
    assert dup.status == "DUPLICATE"
    assert count(session_factory, Node) == 3  # 중복 생성 0

    mutated = copy.deepcopy(payload)  # 같은 request 키, 다른 payload → REJECT
    mutated["judgments"][2] = {"itemId": "m3", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"}
    rej = process_request(session_factory, mutated)
    assert rej.status == "REJECTED"
    assert count(session_factory, Node) == 3


# --- 3. 상태 세탁 강등 -------------------------------------------------------
def test_state_laundering_demoted(session_factory):
    with session_scope(session_factory) as s:
        d = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="d1",
                      node_type="DECISION", category="BACKEND", title="컨슈머 구조 결정")
        a = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="a1",
                      node_type="ACTION", category="BACKEND", title="컨슈머 구현",
                      parent_id=str(d.id), lifecycle_status="COMPLETED", version=1)
        d_id, a_id = str(d.id), str(a.id)

    payload = request_payload(
        meeting_id="M-LAUNDER",
        segments=[seg("s1", "그 컨슈머 작업을 다시 진행 상태로 되돌립시다.", 1000)],
        items=[item("m1", "ACTION", "컨슈머 재개", "완료된 작업을 재개.",
                    [ev("s1", "그 컨슈머 작업을 다시 진행 상태로 되돌립시다.")])],
        judgments=[judgment("m1", "UPDATE_ACTION", targetActionId=a_id, changes={"status": "IN_PROGRESS"})],
        candidates={"decisions": [{"decisionId": d_id, "title": "컨슈머 구조 결정",
                                   "actions": [{"actionId": a_id, "status": "COMPLETED"}]}]},
    )
    res = process_request(session_factory, payload)
    assert res.status == "COMPLETED"
    assert any(d.rule.startswith("ILLEGAL_TRANSITION") for d in res.demoted)
    assert {m.itemId for m in res.minutesOnly} == {"m1"}
    with session_factory() as s:
        a_now = s.get(Node, uuid.UUID(a_id))
        assert a_now.lifecycle_status == "COMPLETED" and a_now.version == 1  # 세탁 차단


# --- 4. 순차 적용 (evidence 시각 순서) ---------------------------------------
def test_sequential_apply_orders_by_evidence_time(session_factory):
    with session_scope(session_factory) as s:
        d = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="d1",
                      node_type="DECISION", category="BACKEND", title="큐 아키텍처 결정")
        a = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="a1",
                      node_type="ACTION", category="BACKEND", title="컨슈머 구현",
                      parent_id=str(d.id), lifecycle_status="IN_PROGRESS", version=1)
        d_id, a_id = str(d.id), str(a.id)

    # 배열 순서는 [늦은 mF, 이른 mC] 이지만 evidence 시각은 mC(2000) < mF(8000).
    payload = request_payload(
        meeting_id="M-SEQ",
        segments=[seg("sC", "컨슈머 구현은 방금 완료했습니다.", 2000),
                  seg("sF", "이제 후속으로 모니터링 대시보드를 만들죠.", 8000)],
        items=[
            item("mF", "ACTION", "모니터링 대시보드 구축", "완료 이후 후속 작업.",
                 [ev("sF", "이제 후속으로 모니터링 대시보드를 만들죠.")]),
            item("mC", "ACTION", "컨슈머 구현 완료", "컨슈머 구현 완료 처리.",
                 [ev("sC", "컨슈머 구현은 방금 완료했습니다.")]),
        ],
        judgments=[
            judgment("mF", "ATTACH", attachTo=d_id),
            judgment("mC", "UPDATE_ACTION", targetActionId=a_id, changes={"status": "COMPLETED"}),
        ],
        candidates={"decisions": [{"decisionId": d_id, "title": "큐 아키텍처 결정",
                                   "actions": [{"actionId": a_id, "status": "IN_PROGRESS"}]}]},
    )
    res = process_request(session_factory, payload)
    assert res.status == "COMPLETED"
    assert res.detail["appliedOrder"] == ["mC", "mF"]  # LLM 배열 순서(mF,mC) 아님
    with session_factory() as s:
        a_now = s.get(Node, uuid.UUID(a_id))
        assert a_now.lifecycle_status == "COMPLETED" and a_now.version == 2
        assert {n.source_item_id for n in s.query(Node).filter_by(source_meeting_id="M-SEQ")} == {"mF"}


# --- 5. optimistic lock ------------------------------------------------------
def test_optimistic_lock_stale_apply_level(session_factory):
    with session_scope(session_factory) as s:
        d = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="d1",
                      node_type="DECISION", category="BACKEND", title="결정")
        a = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="a1",
                      node_type="ACTION", category="BACKEND", title="구현", parent_id=str(d.id),
                      lifecycle_status="IN_PROGRESS", version=1)
        a_id = str(a.id)

    plan = ChangePlan(
        planId="p", projectId=PROJECT, externalMeetingId="M-LOCK", requestId="r",
        lineage=Lineage(),
        commands=[Command(op=PlanOp.UPDATE_ACTION, itemId="m1",
                          sortKey=SortKey(startMs=0, segmentId="s", itemId="m1"),
                          targetActionId=a_id, changes={"status": "COMPLETED"}, expectedVersion=1)],
    )
    # 반영 사이에 version 이 바뀐 상황: 다른 세션에서 v2 로 올린다.
    with session_scope(session_factory) as s:
        n = s.get(Node, uuid.UUID(a_id))
        n.version = 2

    session = session_factory()
    try:
        with pytest.raises(StaleVersionError):
            apply_change_plan(session, plan, CS)
        session.rollback()
    finally:
        session.close()

    with session_factory() as s:
        a_now = s.get(Node, uuid.UUID(a_id))
        assert a_now.version == 2 and a_now.lifecycle_status == "IN_PROGRESS"  # 미반영
        assert s.query(GraphChangeEvent).count() == 0


def test_optimistic_lock_stale_service_level(session_factory, monkeypatch):
    import data_pipeline.pipeline.service as svc

    with session_scope(session_factory) as s:
        d = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="d1",
                      node_type="DECISION", category="BACKEND", title="결정")
        a = seed_node(s, project_id=PROJECT, source_meeting_id="M0", source_item_id="a1",
                      node_type="ACTION", category="BACKEND", title="구현", parent_id=str(d.id),
                      lifecycle_status="IN_PROGRESS", version=1)
        d_id, a_id = str(d.id), str(a.id)

    real = svc.get_node

    def fake(session, nid):  # plan 빌드 시점 expectedVersion 을 실제와 다르게(오래된 값) 보고
        n = real(session, nid)
        return types.SimpleNamespace(version=n.version + 5) if n is not None else None

    monkeypatch.setattr(svc, "get_node", fake)
    payload = request_payload(
        meeting_id="M-LOCK2",
        segments=[seg("s1", "그 작업은 이제 완료되었습니다 확인.", 1000)],
        items=[item("m1", "ACTION", "구현 완료", "완료 처리.", [ev("s1", "그 작업은 이제 완료되었습니다 확인.")])],
        judgments=[judgment("m1", "UPDATE_ACTION", targetActionId=a_id, changes={"status": "COMPLETED"})],
        candidates={"decisions": [{"decisionId": d_id, "title": "결정",
                                   "actions": [{"actionId": a_id, "status": "IN_PROGRESS"}]}]},
    )
    res = process_request(session_factory, payload)
    assert res.status == "STALE"
    with session_factory() as s:
        assert s.get(Node, uuid.UUID(a_id)).version == 1  # 롤백 — 미반영


# --- 6. 원자성 롤백 ----------------------------------------------------------
def test_atomicity_rollback_on_partial_failure(session_factory):
    # c1(정상 CREATE) 이후 c2(존재하지 않는 UPDATE 대상)가 실패 → 전체 롤백.
    plan = ChangePlan(
        planId="p", projectId=PROJECT, externalMeetingId="M-ATOM", requestId="r",
        lineage=Lineage(),
        commands=[
            Command(op=PlanOp.CREATE_DECISION, itemId="m1",
                    sortKey=SortKey(startMs=1000, segmentId="s1", itemId="m1"),
                    nodeType=NodeType.DECISION, category="BACKEND", title="결정 A", content="",
                    parent=ParentRef(), evidence=[EvidenceRef(segmentId="s1", quote="q" * 12)]),
            Command(op=PlanOp.UPDATE_ACTION, itemId="m2",
                    sortKey=SortKey(startMs=2000, segmentId="s2", itemId="m2"),
                    targetActionId=str(uuid.uuid4()), changes={"status": "COMPLETED"}, expectedVersion=1),
        ],
    )
    session = session_factory()
    try:
        with pytest.raises(ApplyError):
            apply_change_plan(session, plan, CS)
        session.rollback()
    finally:
        session.close()

    assert count(session_factory, Node) == 0  # 부분 성공 없음
    assert count(session_factory, GraphChangeEvent) == 0
    assert count(session_factory, OutboxEvent) == 0


# --- 7. PoC 우회 입력 --------------------------------------------------------
def test_bypass_duplicate_itemid(session_factory):
    res = process_request(session_factory, load_fixture("bypass_duplicate_itemid.json"))
    assert res.detail["responseInvalid"]
    assert res.createdNodes == []
    assert count(session_factory, Node) == 0


def test_bypass_short_quote_evidence_invalid(session_factory):
    res = process_request(session_factory, load_fixture("bypass_short_quote.json"))
    assert res.createdNodes == []
    assert any(e["itemId"] == "m1" for e in res.detail["invalidEvidence"])
    assert count(session_factory, Node) == 0


def test_bypass_out_of_candidate_attach(session_factory):
    res = process_request(session_factory, load_fixture("bypass_out_of_candidate.json"))
    assert res.createdNodes == []
    assert any(d.rule == "ATTACH_TARGET_NOT_IN_CANDIDATES" for d in res.demoted)
    assert count(session_factory, Node) == 0
