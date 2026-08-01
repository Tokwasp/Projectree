"""apply 단계 예외. 어떤 예외든 Plan 트랜잭션 전체 롤백을 유발한다 (부분 성공 없음)."""

from __future__ import annotations

from data_pipeline.retrieval.errors import (
    CrossProjectRetrievalError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    RetrievalExecutionError,
)

class ApplyError(Exception):
    """Plan 적용 중 무결성/정합성 오류 → 전체 롤백 (status REJECTED)."""


class StaleVersionError(ApplyError):
    """optimistic lock 불일치 → 전체 롤백 (status STALE, Plan 재생성 경로)."""

    def __init__(self, node_id: str, expected: int | None, actual: int | None) -> None:
        super().__init__(f"stale version on {node_id}: expected {expected}, actual {actual}")
        self.node_id = node_id
        self.expected = expected
        self.actual = actual


class CandidateReviewError(RuntimeError):
    """Base error for Step 4B application-service failures."""


class CandidateNotFoundError(CandidateReviewError):
    pass


class CandidateVersionConflict(CandidateReviewError):
    def __init__(self, candidate_id: str, expected: int, actual: int) -> None:
        self.candidate_id = candidate_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"candidate version conflict: candidate={candidate_id}, "
            f"expected={expected}, actual={actual}"
        )


class CandidateStateError(CandidateReviewError):
    pass


class CandidateValidationError(CandidateReviewError):
    pass


class NodeReviewError(RuntimeError):
    """Base error for editing and finalizing materialized review Nodes."""


class NodeNotFoundError(NodeReviewError):
    pass


class NodeVersionConflict(NodeReviewError):
    def __init__(self, node_id: str, expected: int, actual: int) -> None:
        self.node_id = node_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"node version conflict: node={node_id}, "
            f"expected={expected}, actual={actual}"
        )


class NodeStateError(NodeReviewError):
    pass


class NodeValidationError(NodeReviewError):
    pass


class AnalysisRunNotFoundError(NodeReviewError):
    pass


class AnalysisRunStateError(NodeReviewError):
    pass


class AnalysisRunIncompleteError(AnalysisRunStateError):
    """A Run cannot be completed until all durable outputs exist."""

    def __init__(self, missing_results: list[str]) -> None:
        self.missing_results = tuple(missing_results)
        super().__init__(
            "analysis run is incomplete; missing results: "
            + ", ".join(self.missing_results)
        )


class BModelExecutionError(AnalysisRunStateError):
    pass


class BModelResultValidationError(BModelExecutionError):
    pass


class AnalysisCandidateNotFoundError(NodeReviewError):
    pass


class AnalysisCandidateStateError(NodeReviewError):
    pass


class AnalysisCandidateVersionConflict(NodeReviewError):
    def __init__(self, candidate_id: str, expected: int, actual: int) -> None:
        self.candidate_id = candidate_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"analysis candidate version conflict: candidate={candidate_id}, "
            f"expected={expected}, actual={actual}"
        )


class TranscriptSegmentConflictError(RuntimeError):
    """A stable segment identity was reused with different text."""

    def __init__(
        self,
        *,
        project_id: str,
        external_meeting_id: str,
        segment_id: str,
    ) -> None:
        self.project_id = project_id
        self.external_meeting_id = external_meeting_id
        self.segment_id = segment_id
        super().__init__(
            "transcript segment text conflict: "
            f"project={project_id}, meeting={external_meeting_id}, "
            f"segment={segment_id}"
        )


class LegacyGraphMutationDisabledError(RuntimeError):
    """Legacy graph mutation entry points are quarantined from product flows."""
