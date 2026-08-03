"""Conversion of immutable scenario definitions into public evaluation labels."""

from __future__ import annotations

from data_pipeline.evaluation.contracts import EvaluationCase, LabelStatus

from .scenarios import MAIN_PROJECT_ID, SyntheticCaseSpec, stable_uuid


def to_evaluation_case(case: SyntheticCaseSpec) -> EvaluationCase:
    return EvaluationCase(
        caseId=case.case_id,
        projectId=case.source.project_id,
        sourceNodeId=case.source.node_id,
        sourceNodeType=case.source.node_type,
        expectedAction=case.expected_action,
        expectedTargetNodeId=(
            stable_uuid(MAIN_PROJECT_ID, "node", case.expected_target_key)
            if case.expected_target_key is not None
            else None
        ),
        expectedParentNodeId=(
            stable_uuid(MAIN_PROJECT_ID, "node", case.expected_parent_key)
            if case.expected_parent_key is not None
            else None
        ),
        category=case.category,
        labelStatus=LabelStatus.CONFIRMED,
        notes=case.notes,
    )


def build_gold_labels(cases: list[SyntheticCaseSpec]) -> list[EvaluationCase]:
    return [to_evaluation_case(case) for case in cases]


__all__ = ["build_gold_labels", "to_evaluation_case"]
