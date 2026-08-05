"""Offline threshold mechanics; never writes runtime configuration."""

from __future__ import annotations

from itertools import product

from .contracts import EvaluationCase, LabelStatus, PilotResult


def simulate_thresholds(
    cases: list[EvaluationCase],
    results: list[PilotResult],
    *,
    similarities: tuple[float, ...] = (0.75, 0.8, 0.85),
    margins: tuple[float, ...] = (0.02, 0.05, 0.1),
    confidences: tuple[float, ...] = (0.7, 0.8, 0.9),
) -> dict:
    confirmed = {
        case.case_id: case
        for case in cases
        if case.label_status is LabelStatus.CONFIRMED
    }
    rows = []
    for similarity, margin, confidence in product(
        similarities,
        margins,
        confidences,
    ):
        accepted = 0
        for result in results:
            scores = [candidate.similarity for candidate in result.candidates]
            top1 = scores[0] if scores else -1.0
            top2 = scores[1] if len(scores) > 1 else -1.0
            if (
                top1 >= similarity
                and top1 - top2 >= margin
                and (result.b_model_confidence or 0.0) >= confidence
            ):
                accepted += 1
        rows.append(
            {
                "similarity": similarity,
                "margin": margin,
                "confidence": confidence,
                "accepted": accepted,
            }
        )
    return {
        "status": (
            "MECHANICS_VERIFIED"
            if not confirmed
            else "CONFIRMED_LABEL_SIMULATION"
        ),
        "calibration": (
            "NOT_CALIBRATED" if len(confirmed) < 300 else "CALIBRATION_READY"
        ),
        "confirmedLabelCount": len(confirmed),
        "rows": rows,
    }


__all__ = ["simulate_thresholds"]
