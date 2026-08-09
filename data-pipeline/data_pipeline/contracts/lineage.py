"""Lineage — reproducibility metadata attached to every pipeline result.

Prompt identity is recorded as name/version/SHA rather than a loose string.  All
new fields are optional so fixture-based M1 callers remain backward compatible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "v2.2"
PIPELINE_VERSION = "m1-0.1.0"


class Lineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipelineVersion: str = PIPELINE_VERSION
    schemaVersion: str = SCHEMA_VERSION

    extractionPromptName: str | None = None
    extractionPromptVersion: str | None = None
    extractionPromptSha256: str | None = None

    judgmentPromptName: str | None = None
    judgmentPromptVersion: str | None = None
    judgmentPromptSha256: str | None = None

    promptRendererVersion: str | None = None
    judgmentContractAdapterVersion: str | None = None
    model: str | None = None
    payloadHash: str | None = None

    retrievalConfigVersion: str | None = None
    categorySchemaVersion: str | None = None
    generatedBy: str = "FIXTURE"  # FIXTURE / AI / USER
    extra: dict[str, str] = Field(default_factory=dict)
