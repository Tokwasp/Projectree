"""Metrics that refuse to treat unlabeled data as ground truth."""

from __future__ import annotations

from collections import Counter

from .contracts import EvaluationCase, LabelStatus, PilotResult


def compute_metrics(
    cases: list[EvaluationCase],
    results: list[PilotResult],
) -> dict:
    by_case = {result.case_id: result for result in results}
    confirmed = [
        case for case in cases if case.label_status is LabelStatus.CONFIRMED
    ]
    coverage_count = sum(
        bool(result.candidates) for result in results
    )
    common = {
        "caseCount": len(cases),
        "confirmedLabelCount": len(confirmed),
        "retrievalCoverage": (
            coverage_count / len(results) if results else 0.0
        ),
        "candidateCount": sum(len(result.candidates) for result in results),
        "errorCount": sum(result.status == "ERROR" for result in results),
        "recommendationDistribution": dict(
            Counter(
                result.b_model_action or "NOT_EVALUATED"
                for result in results
            )
        ),
    }
    if not confirmed:
        return {
            **common,
            "precision": None,
            "recall": None,
            "f1": None,
            "targetAccuracy": None,
            "meaningQualityStatus": (
                "N/A — confirmed labels unavailable"
            ),
        }

    expected_merge = [
        case for case in confirmed if case.expected_action == "MERGE"
    ]
    predicted_merge = [
        case
        for case in confirmed
        if by_case.get(case.case_id)
        and by_case[case.case_id].b_model_action == "MERGE"
    ]
    true_merge = [
        case
        for case in predicted_merge
        if case.expected_action == "MERGE"
        and by_case[case.case_id].b_model_target_node_id
        == case.expected_target_node_id
    ]
    precision = (
        len(true_merge) / len(predicted_merge) if predicted_merge else None
    )
    recall = (
        len(true_merge) / len(expected_merge) if expected_merge else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and precision + recall > 0
        else None
    )
    return {
        **common,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "targetAccuracy": (
            len(true_merge) / len(expected_merge)
            if expected_merge
            else None
        ),
        "meaningQualityStatus": "CONFIRMED_LABEL_METRICS",
    }


__all__ = ["compute_metrics"]
