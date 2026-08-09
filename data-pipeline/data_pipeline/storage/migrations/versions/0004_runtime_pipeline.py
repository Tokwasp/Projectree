"""add the review runtime, workers, ingress, and database hardening

Revision ID: 0004_runtime_pipeline
Revises: 0003_review_analysis
Create Date: 2026-08-01

The former unshared 0004-0010 development revisions are composed here as one
deployable revision.  Feature-sized schema steps remain separate so the order
and downgrade symmetry stay reviewable without exposing intermediate revisions.
"""

from __future__ import annotations

from data_pipeline.storage.migrations.steps import (
    analysis_job_outbox,
    analysis_retrieval,
    audio_upload,
    b_model_approval,
    candidate_lifecycle,
    node_relation_integrity,
    outbox_claim_owner,
)

revision = "0004_runtime_pipeline"
down_revision = "0003_review_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Run the only legacy-data precondition before any DDL. This keeps a
    # rejected upgrade fully untouched even on SQLite, whose ALTER TABLE
    # behavior is less transactional than PostgreSQL's.
    outbox_claim_owner.validate_upgrade()
    analysis_retrieval.upgrade()
    b_model_approval.upgrade()
    audio_upload.upgrade()
    candidate_lifecycle.upgrade()
    analysis_job_outbox.upgrade()
    outbox_claim_owner.upgrade()
    node_relation_integrity.upgrade()


def downgrade() -> None:
    node_relation_integrity.downgrade()
    outbox_claim_owner.downgrade()
    analysis_job_outbox.downgrade()
    candidate_lifecycle.downgrade()
    audio_upload.downgrade()
    b_model_approval.downgrade()
    analysis_retrieval.downgrade()
