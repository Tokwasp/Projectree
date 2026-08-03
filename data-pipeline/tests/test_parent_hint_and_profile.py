"""Same-meeting parent hints and the candidate-quality-v1 profile."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import (
    complete_initial_review,
    execute_analysis_retrieval,
    execute_b_model,
    reanalyze_unattached_node,
    run_meeting,
)
from data_pipeline.pipeline.parent_hint import resolve_same_meeting_parent_hint
from data_pipeline.prompts import get_pipeline_profile, render_extraction_prompt
from data_pipeline.storage import Node, NodeCandidate, RetrievalResult

from .support import ev, item, judgment, seg

PROJECT = "proj-hint"
MEETING = "meet-hint"
PROFILE = "candidate-quality-v1"


class _ScriptedClient:
    class _S:
        model = "fake-model"
        temperature = 0.0

    settings = _S()

    def __init__(self, responses: list[dict]):
        self._responses = [json.dumps(r, ensure_ascii=False) for r in responses]
        self.calls = 0

    def complete(self, messages):
        del messages
        raw = self._responses[self.calls]
        self.calls += 1
        return LLMResponse(
            raw_response=raw, input_tokens=10, output_tokens=5,
            total_tokens=15, latency_ms=1,
        )


class _Embedding:
    def embed(self, *, text: str, model: str, dimensions: int):
        del text, model
        return [1.0, *([0.0] * (dimensions - 1))]


def _run_attach_meeting(session_factory, *, meeting=MEETING, project=PROJECT):
    """DECISION m1 + ACTION m2 ATTACHed to m1, via the new profile."""

    decision = item(
        "m1", "DECISION", "회의 처리 서버는 EC2를 사용한다",
        "회의 처리 서버는 EC2를 사용한다",
        [ev("s1", "회의 처리는 EC2로 갑시다")],
    )
    action = item(
        "m2", "ACTION", "EC2에서 RDS 연결을 구성한다",
        "EC2에서 RDS 연결을 구성한다",
        [ev("s2", "제가 EC2에서 RDS 연결 구성하겠습니다")],
    )
    segments = [
        seg("s1", "회의 처리는 EC2로 갑시다"),
        seg("s2", "제가 EC2에서 RDS 연결 구성하겠습니다"),
    ]
    extraction = {"meetingId": meeting, "items": [decision, action]}
    judgments = {
        "meetingId": meeting,
        "judgments": [
            judgment("m1", "NEW_DECISION", category="INFRA"),
            judgment("m2", "ATTACH", attachTo="m1"),
        ],
    }
    run_meeting(
        session_factory,
        meeting_input={
            "requestId": f"req-{meeting}",
            "projectId": project,
            "externalMeetingId": meeting,
            "segments": segments,
        },
        client=_ScriptedClient([extraction, judgments]),
        prompt_profile=PROFILE,
    )


def _approve_all(session_factory, *, project=PROJECT, meeting=MEETING) -> dict[str, Node]:
    with session_factory() as session:
        candidates = session.execute(
            select(NodeCandidate).where(
                NodeCandidate.project_id == project,
                NodeCandidate.external_meeting_id == meeting,
            ).order_by(NodeCandidate.source_item_id)
        ).scalars().all()
        ids = [(c.id, c.source_item_id) for c in candidates]
    nodes: dict[str, Node] = {}
    for candidate_id, source_item in ids:
        complete_initial_review(
            session_factory, candidate_id, project_id=project, actor_id="tester"
        )
    with session_factory() as session:
        for row in session.execute(
            select(Node).where(
                Node.project_id == project, Node.source_meeting_id == meeting
            )
        ).scalars().all():
            session.expunge(row)
            nodes[row.source_item_id] = row
    return nodes


# ----------------------------------------------------------- hint resolve ---


def test_attach_judgment_sets_the_same_meeting_parent_hint(session_factory) -> None:
    _run_attach_meeting(session_factory)
    with session_factory() as session:
        action = session.execute(
            select(NodeCandidate).where(NodeCandidate.source_item_id == "m2")
        ).scalar_one()
        assert action.suggested_parent_candidate_id is not None


def test_hint_resolves_after_both_candidates_are_approved(session_factory) -> None:
    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    with session_factory() as session:
        source = session.get(Node, nodes["m2"].id)
        hint = resolve_same_meeting_parent_hint(session, source)
    assert hint is not None
    assert hint.node_id == nodes["m1"].id
    assert hint.origin == "SAME_MEETING_CANDIDATE"


def test_hint_is_discarded_when_the_parent_was_rejected(session_factory) -> None:
    from data_pipeline.pipeline import reject_candidate

    _run_attach_meeting(session_factory)
    with session_factory() as session:
        parent = session.execute(
            select(NodeCandidate).where(NodeCandidate.source_item_id == "m1")
        ).scalar_one()
        child = session.execute(
            select(NodeCandidate).where(NodeCandidate.source_item_id == "m2")
        ).scalar_one()
        parent_id, child_id = parent.id, child.id
    reject_candidate(
        session_factory, parent_id, project_id=PROJECT, actor_id="tester"
    )
    complete_initial_review(
        session_factory, child_id, project_id=PROJECT, actor_id="tester"
    )
    with session_factory() as session:
        source = session.execute(
            select(Node).where(Node.source_item_id == "m2")
        ).scalar_one()
        assert resolve_same_meeting_parent_hint(session, source) is None


def test_hint_is_discarded_when_the_reviewer_cleared_the_parent(session_factory) -> None:
    from data_pipeline.pipeline import edit_candidate

    _run_attach_meeting(session_factory)
    with session_factory() as session:
        child = session.execute(
            select(NodeCandidate).where(NodeCandidate.source_item_id == "m2")
        ).scalar_one()
        child_id, child_version = child.id, child.version
    edit_candidate(
        session_factory,
        child_id,
        project_id=PROJECT,
        actor_id="tester",
        expected_version=child_version,
        parent_mode="NONE",
    )
    nodes = _approve_all(session_factory)
    with session_factory() as session:
        source = session.get(Node, nodes["m2"].id)
        assert resolve_same_meeting_parent_hint(session, source) is None


def test_hint_never_crosses_projects(session_factory) -> None:
    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    with session_factory() as session:
        # Simulate a corrupted hint: repoint the parent node to another project.
        parent = session.get(Node, nodes["m1"].id)
        parent.project_id = "other-project"
        session.commit()
        source = session.get(Node, nodes["m2"].id)
        assert resolve_same_meeting_parent_hint(session, source) is None


def test_hint_follows_a_merged_parent_to_the_canonical_node(session_factory) -> None:
    from data_pipeline.pipeline import seed_node

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    with session_factory() as session:
        canonical = seed_node(
            session,
            project_id=PROJECT,
            source_meeting_id="older-meeting",
            source_item_id="canonical-decision",
            node_type="DECISION",
            category="INFRA",
            title="EC2 운영 결정(정본)",
            content="EC2 운영 결정.",
            graph_state="ACTIVE",
            evidence=[{"segmentId": "s-old", "quote": "EC2 운영 결정"}],
        )
        parent = session.get(Node, nodes["m1"].id)
        parent.graph_state = "MERGED"
        parent.merged_into_node_id = canonical.id
        session.commit()
        canonical_id = canonical.id
        source = session.get(Node, nodes["m2"].id)
        hint = resolve_same_meeting_parent_hint(session, source)
    assert hint is not None
    assert hint.node_id == canonical_id


# ------------------------------------------------ retrieval force-include ---


def _analyze(session_factory, node: Node):
    with session_factory() as session:
        fresh = session.get(Node, node.id)
        version = fresh.version
    requested = reanalyze_unattached_node(
        session_factory,
        node.id,
        project_id=PROJECT,
        actor_id="tester",
        expected_version=version,
    )
    run_id = requested.run.analysis_run_id
    execute_analysis_retrieval(
        session_factory, run_id, project_id=PROJECT, embedding_client=_Embedding()
    )
    return run_id


def test_parent_without_embedding_is_force_included_in_retrieval(
    session_factory,
) -> None:
    """The freshly created parent has no embedding, so vector search alone
    could never return it. The hint must add it."""

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    run_id = _analyze(session_factory, nodes["m2"])

    with session_factory() as session:
        import uuid as _uuid

        rows = session.execute(
            select(RetrievalResult).where(
                RetrievalResult.analysis_run_id == _uuid.UUID(str(run_id))
            ).order_by(RetrievalResult.rank)
        ).scalars().all()
        target_ids = [row.target_node_id for row in rows]
    assert nodes["m1"].id in target_ids
    hint_row = rows[target_ids.index(nodes["m1"].id)]
    assert hint_row.similarity == 0.0  # no embedding yet -> neutral similarity


def test_b_model_payload_flags_the_hint_candidate(session_factory) -> None:
    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    run_id = _analyze(session_factory, nodes["m2"])

    captured: dict = {}

    class _CapturingClient:
        def recommend(self, *, source_node, retrieval_candidates, model):
            captured["candidates"] = retrieval_candidates
            # The hint parent is still UNATTACHED here, so ATTACHED_TO would be
            # rejected by _validate_target; the contract-conform answer is
            # CREATE_NEW with the relationship recorded in the reason.
            return {
                "recommendation": "CREATE_NEW",
                "suggestedTitle": source_node["title"],
                "suggestedContent": source_node["content"],
                "reason": "같은 회의 상위 결정(아직 UNATTACHED)의 실행이므로 독립 생성",
            }

    result = execute_b_model(
        session_factory,
        run_id,
        project_id=PROJECT,
        client=_CapturingClient(),
        model="test-b",
        model_version="v1",
    )
    assert result.candidate is not None
    flagged = [
        row for row in captured["candidates"]
        if row.get("sameMeetingSuggestedParent")
    ]
    assert len(flagged) == 1
    assert flagged[0]["nodeId"] == str(nodes["m1"].id)
    assert flagged[0]["parentHintOrigin"] == "SAME_MEETING_CANDIDATE"


def test_hint_is_deduplicated_against_vector_results(session_factory) -> None:
    """When the parent already has a READY embedding it arrives via vector
    search; the hint must not create a second row."""

    from datetime import datetime, timezone

    from data_pipeline.config import load_settings
    from data_pipeline.storage import NodeEmbedding

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    retrieval = load_settings().retrieval
    with session_factory() as session:
        session.add(
            NodeEmbedding(
                node_id=nodes["m1"].id,
                embedding_version=retrieval.embedding_version,
                embedding_model=retrieval.embedding_model,
                dimension=retrieval.embedding_dim,
                embedded_text_hash="hint-test",
                embedding=[1.0, *([0.0] * (retrieval.embedding_dim - 1))],
                status="READY",
                embedded_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    run_id = _analyze(session_factory, nodes["m2"])
    with session_factory() as session:
        import uuid as _uuid

        rows = session.execute(
            select(RetrievalResult).where(
                RetrievalResult.analysis_run_id == _uuid.UUID(str(run_id))
            )
        ).scalars().all()
        matching = [r for r in rows if r.target_node_id == nodes["m1"].id]
    assert len(matching) == 1
    assert matching[0].similarity > 0.9  # real vector match, not the 0.0 hint row


# --------------------------------------------------- candidate profile ---


def test_new_profile_is_registered_and_default_is_untouched() -> None:
    profile = get_pipeline_profile(PROFILE)
    assert profile.status == "CANDIDATE"
    assert get_pipeline_profile().name == "poc-lts"
    # Frozen LTS SHAs unchanged.
    lts = get_pipeline_profile("poc-lts")
    assert lts.extraction_asset.sha256 == (
        "d719d6bcfbf544268bede4a79b17cf04eeffd2ce81f50c86eb624db3482b7b1d"
    )


def test_profile_prompt_contains_the_new_rules() -> None:
    rendered = render_extraction_prompt(
        PROFILE,
        segments=[{"segmentId": "s1", "text": "hello"}],
        category_values=["BACKEND", "INFRA"],
        meeting_id="m-x",
    )
    assert "lifecycleStatus" not in rendered   # removed with the lifecycle domain
    assert "발화 겹침" in rendered            # meeting-noise exclusion
    assert "임의의 고유명사로 확정하지 마라" in rendered  # uncertain tech terms
    assert "다른 팀원의 동의가 없어도 ACTION" in rendered
    assert "{{SEGMENTS_JSON}}" not in rendered


def test_new_profile_output_still_becomes_a_typed_node(session_factory) -> None:
    """The profile keeps driving type and parent; only lifecycle is gone."""

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    assert nodes["m2"].node_type == "ACTION"
    assert not hasattr(nodes["m2"], "lifecycle_status")


def test_identity_judgments_survive_the_new_profile(session_factory) -> None:
    _run_attach_meeting(session_factory)
    with session_factory() as session:
        dispositions = {
            c.source_item_id: c.suggested_disposition
            for c in session.execute(select(NodeCandidate)).scalars().all()
        }
    assert dispositions == {"m1": "NEW_DECISION", "m2": "ATTACH"}


def test_demotions_are_persisted_in_request_warnings(session_factory) -> None:
    """A silently demoted judgment must leave a durable trace.

    Found in the live E2E: one 7-char quote invalidated a DECISION's evidence,
    EVIDENCE_INVALID demoted it and cascade-demoted its ATTACH children — and
    request.warnings stayed empty, so no API consumer could see why.
    """

    decision = item(
        "m1", "DECISION", "EC2 사용 결정", "EC2 사용 결정",
        [ev("s1", "회의 처리는 EC2로 갑시다")],
    )
    # Second quote is deliberately shorter than the 10-char minimum.
    decision["evidence"].append({"segmentId": "s2", "quote": "네, 좋아요."})
    action = item(
        "m2", "ACTION", "RDS 연결 구성", "RDS 연결 구성",
        [ev("s2", "네, 좋아요. 제가 RDS 연결 구성하겠습니다")],
    )
    segments = [
        seg("s1", "회의 처리는 EC2로 갑시다"),
        seg("s2", "네, 좋아요. 제가 RDS 연결 구성하겠습니다"),
    ]
    run_meeting(
        session_factory,
        meeting_input={
            "requestId": "req-warn",
            "projectId": PROJECT,
            "externalMeetingId": "meet-warn",
            "segments": segments,
        },
        client=_ScriptedClient([
            {"meetingId": "meet-warn", "items": [decision, action]},
            {"meetingId": "meet-warn", "judgments": [
                judgment("m1", "NEW_DECISION", category="INFRA"),
                judgment("m2", "ATTACH", attachTo="m1"),
            ]},
        ]),
        prompt_profile=PROFILE,
    )

    from data_pipeline.storage import Request

    with session_factory() as session:
        request = session.execute(
            select(Request).where(Request.external_meeting_id == "meet-warn")
        ).scalar_one()
        dispositions = {
            c.source_item_id: c.suggested_disposition
            for c in session.execute(
                select(NodeCandidate).where(
                    NodeCandidate.external_meeting_id == "meet-warn"
                )
            ).scalars().all()
        }
    # The demotion behaviour itself is locked product policy...
    assert dispositions["m1"] == "MINUTES_ONLY"
    # ...but it must no longer be silent.
    assert any(
        w.startswith("DEMOTED:m1:EVIDENCE_INVALID") for w in request.warnings
    ), request.warnings


def test_reanalyze_creates_a_fresh_attempt_when_the_target_drifted(
    session_factory,
) -> None:
    """Live-E2E finding: a MERGE bumping the target version left sibling
    candidates permanently stuck — reanalyze reused the COMPLETED run because
    the input hash only covers the source node. A stale PENDING candidate
    target must force a new attempt instead of reusing the run."""

    from data_pipeline.pipeline import seed_node

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)

    # Give the ACTION a merge-able ACTIVE DECISION target via retrieval + B.
    from data_pipeline.config import load_settings
    from data_pipeline.storage import NodeEmbedding
    from datetime import datetime, timezone

    retrieval = load_settings().retrieval
    source = nodes["m2"]
    with session_factory() as session:
        target = seed_node(
            session,
            project_id=PROJECT,
            source_meeting_id="prior-meeting",
            source_item_id="prior-decision",
            node_type="ACTION",
            category=source.category,
            title="기존 RDS 연결 작업",
            content="기존 RDS 연결 작업.",
            graph_state="ACTIVE",
            evidence=[{"segmentId": "p1", "quote": "기존 RDS 연결 작업"}],
        )
        session.add(
            NodeEmbedding(
                node_id=target.id,
                embedding_version=retrieval.embedding_version,
                embedding_model=retrieval.embedding_model,
                dimension=retrieval.embedding_dim,
                embedded_text_hash="drift-seed",
                embedding=[1.0, *([0.0] * (retrieval.embedding_dim - 1))],
                status="READY",
                embedded_at=datetime.now(timezone.utc),
            )
        )
        target_id = target.id
        session.commit()

    requested = reanalyze_unattached_node(
        session_factory, source.id, project_id=PROJECT,
        actor_id="tester", expected_version=source.version,
    )
    run_id = requested.run.analysis_run_id
    execute_analysis_retrieval(
        session_factory, run_id, project_id=PROJECT, embedding_client=_Embedding()
    )

    class _MergeClient:
        def recommend(self, *, source_node, retrieval_candidates, model):
            return {
                "recommendation": "MERGE",
                "targetNodeId": str(target_id),
                "suggestedTitle": "병합",
                "suggestedContent": "병합 내용",
                "reason": "같은 작업",
            }

    execute_b_model(
        session_factory, run_id, project_id=PROJECT,
        client=_MergeClient(), model="t", model_version="v1",
    )

    # Simulate graph drift: someone else's approval bumped the target version.
    with session_factory() as session:
        drifted = session.get(Node, target_id)
        drifted.version += 1
        session.commit()
        fresh_source = session.get(Node, source.id)
        fresh_version = fresh_source.version

    retried = reanalyze_unattached_node(
        session_factory, source.id, project_id=PROJECT,
        actor_id="tester", expected_version=fresh_version,
    )
    assert retried.created is True          # NOT a reuse of the stale run
    assert str(retried.run.analysis_run_id) != str(run_id)


def test_repeated_reanalyze_does_not_explode_attempts(session_factory) -> None:
    """The stale-target gate must not turn every reanalyze into a new attempt.

    Code-review concern (Q3): _pending_candidate_target_is_stale forces a fresh
    attempt. If that gate were reachable while a PENDING/RUNNING run already
    exists, a user hammering reanalyze would grow attempt without bound. It is
    not: the PENDING/RUNNING branch returns created=False first.
    """

    from data_pipeline.storage import NodeAnalysisRun

    _run_attach_meeting(session_factory)
    nodes = _approve_all(session_factory)
    source = nodes["m2"]

    created_flags = []
    for _ in range(4):
        with session_factory() as session:
            version = session.get(Node, source.id).version
        result = reanalyze_unattached_node(
            session_factory, source.id, project_id=PROJECT,
            actor_id="tester", expected_version=version,
        )
        created_flags.append(result.created)

    # First call creates the run; the rest reuse the still-PENDING one.
    assert created_flags == [True, False, False, False]
    with session_factory() as session:
        runs = session.execute(
            select(NodeAnalysisRun).where(
                NodeAnalysisRun.source_node_id == source.id
            )
        ).scalars().all()
        assert len(runs) == 1
        assert max(r.attempt for r in runs) == 1


def test_demotion_warnings_contain_no_meeting_content(session_factory) -> None:
    """request.warnings must carry identifiers and rule names only.

    The demote() rules are constant strings plus enum/field names; a quote or
    title leaking in here would put meeting content into an operational field.
    """

    decision = item(
        "m1", "DECISION", "EC2 사용 결정", "EC2 사용 결정",
        [ev("s1", "회의 처리는 EC2로 갑시다")],
    )
    decision["evidence"].append({"segmentId": "s2", "quote": "짧음"})
    segments = [
        seg("s1", "회의 처리는 EC2로 갑시다"),
        seg("s2", "짧음 그리고 비밀스러운 회의 원문 내용이 여기에 있다"),
    ]
    run_meeting(
        session_factory,
        meeting_input={
            "requestId": "req-warn2",
            "projectId": PROJECT,
            "externalMeetingId": "meet-warn2",
            "segments": segments,
        },
        client=_ScriptedClient([
            {"meetingId": "meet-warn2", "items": [decision]},
            {"meetingId": "meet-warn2",
             "judgments": [judgment("m1", "NEW_DECISION", category="INFRA")]},
        ]),
        prompt_profile=PROFILE,
    )

    from data_pipeline.storage import Request

    with session_factory() as session:
        warnings = session.execute(
            select(Request).where(Request.external_meeting_id == "meet-warn2")
        ).scalar_one().warnings

    assert any(w.startswith("DEMOTED:m1:") for w in warnings), warnings
    blob = " ".join(warnings)
    for leaked in ("회의 처리는 EC2로", "비밀스러운", "짧음", "EC2 사용 결정"):
        assert leaked not in blob, f"meeting content leaked into warnings: {leaked}"
