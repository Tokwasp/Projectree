"""Domain exception to HTTP status mapping.

Registered most-specific-first: several domain errors are subclasses of one
another (AnalysisRunIncompleteError < AnalysisRunStateError, BModelResultValidationError
< BModelExecutionError < AnalysisRunStateError, CrossProjectRetrievalError <
RetrievalExecutionError), so registration order is load-bearing.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from data_pipeline.meeting_summary import (
    MeetingSummaryConflictError,
    MeetingSummaryNotFoundError,
    MeetingSummarySourceError,
)

from data_pipeline.pipeline.errors import (
    AnalysisCandidateNotFoundError,
    AnalysisCandidateStateError,
    AnalysisCandidateVersionConflict,
    AnalysisRunIncompleteError,
    AnalysisRunNotFoundError,
    AnalysisRunStateError,
    ApplyError,
    BModelExecutionError,
    BModelResultValidationError,
    CandidateNotFoundError,
    CandidateReviewError,
    CandidateStateError,
    CandidateValidationError,
    CandidateVersionConflict,
    CrossProjectRetrievalError,
    DependentAnalysisBlockedError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    LegacyGraphMutationDisabledError,
    EvidenceValidationError,
    GenerationRunNotFoundError,
    GenerationRunStateError,
    GraphIntegrityError,
    GraphMutationValidationError,
    MergeNotReversibleError,
    NodeNotFoundError,
    NodeReviewError,
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
    RetrievalExecutionError,
    StaleVersionError,
)

logger = logging.getLogger(__name__)


def _problem(
    status_code: int,
    code: str,
    message: str,
    extra: dict | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if extra:
        body["error"].update(extra)
    return JSONResponse(status_code=status_code, content=body)


def _version_extra(exc) -> dict:
    expected = getattr(exc, "expected", None)
    actual = getattr(exc, "actual", None)
    if expected is None and actual is None:
        return {}
    return {"expectedVersion": expected, "actualVersion": actual}


#: (exception, status, code) in registration order - subclasses first.
_MAPPING: list[tuple[type[Exception], int, str]] = [
    # 404
    (MeetingSummaryNotFoundError, 404, "MEETING_SUMMARY_NOT_FOUND"),
    (CandidateNotFoundError, 404, "CANDIDATE_NOT_FOUND"),
    (NodeNotFoundError, 404, "NODE_NOT_FOUND"),
    (AnalysisRunNotFoundError, 404, "ANALYSIS_RUN_NOT_FOUND"),
    (AnalysisCandidateNotFoundError, 404, "ANALYSIS_CANDIDATE_NOT_FOUND"),
    (GenerationRunNotFoundError, 404, "GENERATION_RUN_NOT_FOUND"),
    # 409 optimistic locking
    (CandidateVersionConflict, 409, "VERSION_CONFLICT"),
    (NodeVersionConflict, 409, "VERSION_CONFLICT"),
    (AnalysisCandidateVersionConflict, 409, "VERSION_CONFLICT"),
    (StaleVersionError, 409, "VERSION_CONFLICT"),
    # 422 validation (before the state errors they may subclass)
    (MeetingSummarySourceError, 422, "MEETING_SUMMARY_SOURCE_INVALID"),
    (CandidateValidationError, 422, "VALIDATION_FAILED"),
    (BModelResultValidationError, 422, "B_MODEL_RESULT_INVALID"),
    (EmbeddingValidationError, 422, "EMBEDDING_INVALID"),
    (NodeValidationError, 422, "VALIDATION_FAILED"),
    (EvidenceValidationError, 422, "EVIDENCE_INVALID"),
    (GraphMutationValidationError, 422, "GRAPH_MUTATION_INVALID"),
    # 409 invalid state
    (MeetingSummaryConflictError, 409, "MEETING_SUMMARY_CONFLICT"),
    (AnalysisRunIncompleteError, 409, "ANALYSIS_RUN_INCOMPLETE"),
    (
        DependentAnalysisBlockedError,
        409,
        "DEPENDENT_ANALYSIS_BLOCKED",
    ),
    (CandidateStateError, 409, "INVALID_STATE"),
    (NodeStateError, 409, "INVALID_STATE"),
    (AnalysisCandidateStateError, 409, "INVALID_STATE"),
    (MergeNotReversibleError, 409, "MERGE_NOT_REVERSIBLE"),
    (GenerationRunStateError, 409, "GENERATION_RUN_STATE"),
    # 502 upstream providers
    (BModelExecutionError, 502, "B_MODEL_FAILED"),
    (EmbeddingGenerationError, 502, "EMBEDDING_FAILED"),
    (AnalysisRunStateError, 409, "INVALID_STATE"),
    # 500 internal / isolation breach
    (CrossProjectRetrievalError, 500, "CROSS_PROJECT_RETRIEVAL"),
    (RetrievalExecutionError, 500, "RETRIEVAL_FAILED"),
    (LegacyGraphMutationDisabledError, 403, "LEGACY_PATH_DISABLED"),
    (GraphIntegrityError, 500, "GRAPH_INTEGRITY_ERROR"),
    (ApplyError, 500, "APPLY_FAILED"),
    (CandidateReviewError, 500, "REVIEW_FAILED"),
    (NodeReviewError, 500, "REVIEW_FAILED"),
]


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status_code, code in _MAPPING:
        app.add_exception_handler(
            exc_type, _make_handler(status_code, code)
        )


def _make_handler(status_code: int, code: str):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        del request
        if status_code >= 500:
            logger.exception("request failed error_type=%s", type(exc).__name__)
        else:
            logger.info(
                "request rejected status=%d code=%s error_type=%s",
                status_code,
                code,
                type(exc).__name__,
            )
        # Domain messages describe state and identifiers, never meeting content.
        return _problem(status_code, code, str(exc), _version_extra(exc))

    return handler


__all__ = ["register_exception_handlers"]
