from __future__ import annotations

import uuid

from data_pipeline.evaluation.contracts import EvaluationCase, PilotResult
from data_pipeline.evaluation.metrics import compute_metrics


def test_unreviewed_cases_never_produce_meaning_accuracy() -> None:
    node_id = uuid.uuid4()
    cases = [
        EvaluationCase(
            caseId="case-001",
            projectId="pilot",
            sourceNodeId=node_id,
        )
    ]
    results = [
        PilotResult(
            caseId="case-001",
            projectId="pilot",
            sourceNodeId=node_id,
            status="COMPLETED",
            reason="RETRIEVAL_COMPLETED",
        )
    ]

    metrics = compute_metrics(cases, results)

    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
    assert metrics["meaningQualityStatus"].startswith("N/A")
