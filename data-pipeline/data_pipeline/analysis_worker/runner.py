"""Analysis Worker: drains analysis_job, runs Retrieval and the B model.

This is the asynchronous boundary. The HTTP layer enqueues and returns 202; all
embedding, pgvector Retrieval and B-model work happens here so no user request
and no SQS message is held open while a person reviews.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from data_pipeline.jobs import (
    ANALYSIS_QUEUED,
    FINAL_REVIEW_READY,
    PIPELINE_FAILED,
    ClaimedAnalysisJob,
    claim_next_analysis_job,
    complete_analysis_job,
    emit_outbox_event,
    fail_analysis_job,
)
from data_pipeline.pipeline import (
    execute_analysis_retrieval,
    execute_b_model,
    reanalyze_unattached_node,
)
from data_pipeline.pipeline.errors import (
    AnalysisRunStateError,
    BModelExecutionError,
    EmbeddingGenerationError,
    EmbeddingValidationError,
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    RetrievalExecutionError,
)
from data_pipeline.storage import Node

logger = logging.getLogger(__name__)

#: Failures that will never succeed on a retry - fail the job immediately.
NON_RETRYABLE = (
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    EmbeddingValidationError,
)

#: Failures worth another attempt (transient provider/network/lock problems).
RETRYABLE = (
    EmbeddingGenerationError,
    RetrievalExecutionError,
    BModelExecutionError,
    AnalysisRunStateError,
)


@dataclass(frozen=True)
class AnalysisWorkerResult:
    claimed: int
    succeeded: int
    failed: int
    skipped: int


class AnalysisWorker:
    def __init__(
        self,
        *,
        session_factory,
        embedding_client,
        b_model_client,
        b_model_version: str = "v1",
        actor_id: str = "analysis-worker",
    ):
        self._session_factory = session_factory
        self._embedding_client = embedding_client
        self._b_model_client = b_model_client
        self._b_model_version = b_model_version
        self._actor_id = actor_id

    def run_once(self) -> AnalysisWorkerResult:
        job = claim_next_analysis_job(self._session_factory)
        if job is None:
            return AnalysisWorkerResult(0, 0, 0, 0)
        try:
            completed = self._process(job)
        except NON_RETRYABLE as exc:
            owned = self._fail(job, exc, retryable=False)
            return (
                AnalysisWorkerResult(1, 0, 1, 0)
                if owned
                else AnalysisWorkerResult(1, 0, 0, 1)
            )
        except RETRYABLE as exc:
            owned = self._fail(job, exc, retryable=True)
            return (
                AnalysisWorkerResult(1, 0, 1, 0)
                if owned
                else AnalysisWorkerResult(1, 0, 0, 1)
            )
        except Exception as exc:  # unknown: retry, but bounded by max_attempts
            owned = self._fail(job, exc, retryable=True)
            return (
                AnalysisWorkerResult(1, 0, 1, 0)
                if owned
                else AnalysisWorkerResult(1, 0, 0, 1)
            )
        return (
            AnalysisWorkerResult(1, 1, 0, 0)
            if completed
            else AnalysisWorkerResult(1, 0, 0, 1)
        )

    def run_forever(self, *, idle_sleep_seconds: float = 2.0) -> None:
        while True:
            try:
                result = self.run_once()
            except KeyboardInterrupt:
                return
            except Exception:
                logger.exception("analysis worker loop failed; continuing")
                time.sleep(idle_sleep_seconds)
                continue
            if result.claimed == 0:
                time.sleep(idle_sleep_seconds)

    # -- internals -------------------------------------------------------
    def _process(self, job: ClaimedAnalysisJob) -> bool:
        node_version = self._current_node_version(
            job.node_id,
            project_id=job.project_id,
        )
        requested = reanalyze_unattached_node(
            self._session_factory,
            job.node_id,
            project_id=job.project_id,
            actor_id=self._actor_id,
            expected_version=node_version,
        )
        run_id = requested.run.analysis_run_id
        # No ANALYSIS_QUEUED here: the API already emitted one per node inside
        # the enqueue transaction. Emitting again would give the same logical
        # event a second eventId, which consumer-side dedup cannot collapse.

        execute_analysis_retrieval(
            self._session_factory,
            run_id,
            project_id=job.project_id,
            embedding_client=self._embedding_client,
        )
        recommendation = execute_b_model(
            self._session_factory,
            run_id,
            project_id=job.project_id,
            client=self._b_model_client,
            model_version=self._b_model_version,
        )

        payload = {
            "nodeId": str(job.node_id),
            "analysisRunId": str(run_id),
            "analysisCandidateId": (
                recommendation.candidate.candidate_id
                if recommendation.candidate is not None
                else None
            ),
            "bModelCalled": recommendation.b_model_called,
        }
        # The event is staged on the SAME transaction that flips the job to
        # SUCCEEDED, so the completion and the notification commit together.
        completed = complete_analysis_job(
            self._session_factory,
            job_id=job.job_id,
            claim_token=job.claim_token,
            analysis_run_id=uuid.UUID(str(run_id)),
            on_session=lambda session: self._stage(
                session, job, event_type=FINAL_REVIEW_READY, payload=payload
            ),
        )
        if not completed:
            logger.info(
                "analysis job completion ignored after claim ownership changed "
                "job_id=%s node_id=%s",
                job.job_id,
                job.node_id,
            )
        return completed

    def _current_node_version(
        self,
        node_id: uuid.UUID,
        *,
        project_id: str,
    ) -> int:
        with self._session_factory() as session:
            node = session.execute(
                select(Node).where(
                    Node.id == node_id,
                    Node.project_id == project_id,
                )
            ).scalar_one_or_none()
            if node is None:
                raise NodeNotFoundError(f"node not found: {node_id}")
            return node.version

    def _fail(
        self,
        job: ClaimedAnalysisJob,
        exc: Exception,
        *,
        retryable: bool,
    ) -> bool:
        logger.warning(
            "analysis job failed job_id=%s node_id=%s attempt=%d error_type=%s "
            "retryable=%s",
            job.job_id,
            job.node_id,
            job.attempt,
            type(exc).__name__,
            retryable,
        )
        # PIPELINE_FAILED is staged on the same transaction that writes the
        # terminal FAILED status, so the two cannot diverge.
        status = fail_analysis_job(
            self._session_factory,
            job_id=job.job_id,
            claim_token=job.claim_token,
            failure_code=type(exc).__name__,
            error=str(exc),
            retryable=retryable,
            on_terminal_failure=lambda session: self._stage(
                session,
                job,
                event_type=PIPELINE_FAILED,
                payload={
                    "nodeId": str(job.node_id),
                    "stage": "ANALYSIS",
                    "failureCode": type(exc).__name__,
                },
            ),
        )
        if status == "UNOWNED":
            logger.info(
                "analysis job failure ignored after claim ownership changed "
                "job_id=%s node_id=%s",
                job.job_id,
                job.node_id,
            )
            return False
        return True

    def _stage(
        self,
        session,
        job: ClaimedAnalysisJob,
        *,
        event_type: str,
        payload: dict,
    ) -> None:
        """Stage an event on the caller's session; never commits by itself."""

        emit_outbox_event(
            session,
            event_type=event_type,
            aggregate_type="node",
            aggregate_id=str(job.node_id),
            project_id=job.project_id,
            payload={"meetingId": job.external_meeting_id, **payload},
        )


__all__ = ["AnalysisWorker", "AnalysisWorkerResult", "NON_RETRYABLE", "RETRYABLE"]
