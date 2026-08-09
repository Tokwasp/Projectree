from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from tests.evaluation_support.contracts import EvaluationCase, LabelStatus


def test_label_contract_uses_public_aliases() -> None:
    node_id = uuid.uuid4()
    case = EvaluationCase.model_validate(
        {
            "caseId": "case-001",
            "projectId": "15",
            "sourceNodeId": str(node_id),
            "expectedAction": None,
            "expectedTargetNodeId": None,
            "expectedParentNodeId": None,
            "labelStatus": "UNREVIEWED",
            "notes": None,
        }
    )

    assert case.source_node_id == node_id
    assert case.label_status is LabelStatus.UNREVIEWED
    assert case.model_dump(by_alias=True)["caseId"] == "case-001"


def test_unknown_label_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluationCase(
            caseId="case-001",
            projectId="15",
            sourceNodeId=uuid.uuid4(),
            labelStatus="GUESSED",
        )
