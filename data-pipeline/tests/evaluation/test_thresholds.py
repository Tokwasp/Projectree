from __future__ import annotations

import uuid

from tests.evaluation_support.contracts import (
    EvaluationCase,
    PilotResult,
    RetrievedCandidate,
)
from tests.evaluation_support.thresholds import simulate_thresholds


def test_unlabeled_thresholds_verify_mechanics_without_calibration() -> None:
    source = uuid.uuid4()
    target = uuid.uuid4()
    cases = [
        EvaluationCase(
            caseId="case-001",
            projectId="pilot",
            sourceNodeId=source,
        )
    ]
    results = [
        PilotResult(
            caseId="case-001",
            projectId="pilot",
            sourceNodeId=source,
            status="COMPLETED",
            reason="RETRIEVAL_COMPLETED",
            bModelConfidence=0.9,
            candidates=[
                RetrievedCandidate(
                    nodeId=target,
                    rank=1,
                    similarity=0.9,
                    nodeType="DECISION",
                    typeValid=True,
                )
            ],
        )
    ]

    simulation = simulate_thresholds(
        cases,
        results,
        similarities=(0.8,),
        margins=(0.05,),
        confidences=(0.8,),
    )

    assert simulation["status"] == "MECHANICS_VERIFIED"
    assert simulation["calibration"] == "NOT_CALIBRATED"
    assert simulation["rows"][0]["accepted"] == 1
