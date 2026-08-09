from __future__ import annotations

from tests.evaluation_support.extraction import extract_pilot_cases
from data_pipeline.pipeline import seed_node


def _seed(session, *, project: str, item: str, node_type: str, state="ACTIVE"):
    return seed_node(
        session,
        project_id=project,
        source_meeting_id="evaluation-meeting",
        source_item_id=item,
        node_type=node_type,
        category="INFRA",
        title=f"evaluation-{item}",
        graph_state=state,
    )


def test_extraction_is_project_scoped_and_excludes_non_searchable(
    session_factory,
) -> None:
    with session_factory() as session:
        expected = {
            _seed(session, project="pilot", item="d1", node_type="DECISION").id,
            _seed(session, project="pilot", item="a1", node_type="ACTION").id,
            _seed(session, project="pilot", item="i1", node_type="ISSUE").id,
        }
        _seed(
            session,
            project="pilot",
            item="excluded",
            node_type="DECISION",
            state="EXCLUDED",
        )
        _seed(session, project="other", item="other", node_type="DECISION")
        session.commit()

    with session_factory() as session:
        cases = extract_pilot_cases(
            session,
            project_id="pilot",
            limit=10,
        )

    assert {case.source_node_id for case in cases} == expected
    assert all(case.project_id == "pilot" for case in cases)


def test_extraction_limit_is_bounded(session_factory) -> None:
    with session_factory() as session:
        for index in range(8):
            _seed(
                session,
                project="pilot",
                item=f"d{index}",
                node_type="DECISION",
            )
        session.commit()
    with session_factory() as session:
        assert len(
            extract_pilot_cases(session, project_id="pilot", limit=5)
        ) == 5
