"""Two-stage node-generation chain with version-locked pipeline profiles.

The production default is the validated A/PoC semantic pair:

    extraction v3 LTS -> judgment v4 LTS -> server contract adapter

The rewritten M2 pair is retained as ``m2-current-candidate`` for explicit
comparison or rollback.  Profile selection always changes extraction and
judgment together; production code cannot accidentally cross-pair them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_pipeline.adapters import JudgmentContractAdapter, adapter_for_kind
from data_pipeline.contracts import CategorySet, Lineage, ProposalPersistResult
from data_pipeline.llm import ChatClient
from data_pipeline.prompts import (
    DEFAULT_PIPELINE_PROFILE_NAME,
    PipelineProfile,
    get_pipeline_profile,
    render_extraction_prompt,
    render_judgment_prompt,
)

from .repository import normalize_extraction_items
from .service import (
    GENERATION_INPUT_HASH_VERSION,
    claim_generation_request,
    finalize_generation_candidates,
    mark_generation_failed,
    payload_hash,
)

NODE_GENERATION_PIPELINE_VERSION = "node-generation-0.3.0"
# Compatibility export used by Step-2 callers.
M2_PIPELINE_VERSION = NODE_GENERATION_PIPELINE_VERSION

CREDIT_PER_INPUT_TOKEN = 0.0175
CREDIT_PER_OUTPUT_TOKEN = 0.14
logger = logging.getLogger(__name__)


def estimate_credits(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * CREDIT_PER_INPUT_TOKEN + output_tokens * CREDIT_PER_OUTPUT_TOKEN


def parse_json_object(raw: str) -> tuple[dict | None, str | None]:
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc.msg} (line {exc.lineno})"
    if not isinstance(value, dict):
        return None, "최상위 JSON 값은 객체여야 합니다."
    return value, None


def generation_input_hash(
    *,
    meeting_input: dict,
    pipeline_version: str,
    profile: PipelineProfile,
    category_set: CategorySet,
    term_corrections: list[dict[str, str]] | None,
    adapter_version: str,
    model: str,
    temperature: float | None,
) -> str:
    """Hash only deterministic inputs available before generation."""

    segments = []
    for position, segment in enumerate(meeting_input.get("segments", [])):
        segments.append({
            "segmentId": segment.get("segmentId"),
            "sequenceNo": segment.get("sequenceNo", position),
            "startMs": segment.get("startMs"),
            "endMs": segment.get("endMs"),
            "speakerLabel": segment.get("speakerLabel"),
            "text": segment.get("text", ""),
        })
    value = {
        "version": GENERATION_INPUT_HASH_VERSION,
        "identity": {
            "projectId": meeting_input["projectId"],
            "externalMeetingId": meeting_input["externalMeetingId"],
        },
        "pipelineVersion": pipeline_version,
        "pipelineProfile": profile.name,
        "prompts": {
            "extraction": {
                "name": profile.extraction_asset.name,
                "version": profile.extraction_asset.version,
                "sha256": profile.extraction_asset.sha256,
            },
            "judgment": {
                "name": profile.judgment_asset.name,
                "version": profile.judgment_asset.version,
                "sha256": profile.judgment_asset.sha256,
            },
            "rendererVersion": profile.renderer_version,
            "judgmentAdapterVersion": adapter_version,
        },
        "categories": {
            "schemaVersion": category_set.schema_version,
            "values": list(category_set.values),
        },
        "termCorrections": list(term_corrections or []),
        "segments": segments,
        "candidates": meeting_input.get("candidates") or {"decisions": []},
        "llm": {"model": model, "temperature": temperature},
    }
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class StageResult:
    prompt_sha256: str
    raw_response: str
    parsed: dict | None
    error: str | None
    error_code: str | None
    attempts: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    credit_usage: float
    attempt_diagnostics: list[dict] = field(default_factory=list)


@dataclass
class JudgmentOnlyRunResult:
    profile_name: str
    judgment: StageResult
    raw_judgments: list[dict]
    adapted_judgments: list[dict]
    prompt: str
    adapter_version: str

    @property
    def credits(self) -> float:
        return self.judgment.credit_usage


@dataclass
class GenerationOnlyRunResult:
    """Explicit evaluation utility; it intentionally does not claim/deduplicate."""

    profile_name: str
    extraction: StageResult
    judgment: StageResult
    raw_items: list[dict]
    items: list[dict]
    raw_judgments: list[dict]
    judgments: list[dict]
    dropped_item_ids: list[str]
    extraction_prompt: str
    judgment_prompt: str
    adapter_version: str

    @property
    def input_tokens(self) -> int:
        return self.extraction.input_tokens + self.judgment.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.extraction.output_tokens + self.judgment.output_tokens

    @property
    def credits(self) -> float:
        return self.extraction.credit_usage + self.judgment.credit_usage


@dataclass
class MeetingRunResult:
    meeting_id: str
    proposal_result: ProposalPersistResult
    extraction: StageResult
    judgment: StageResult
    items: list[dict]
    judgments: list[dict]
    dropped_item_ids: list[str]
    prompt_profile: str
    output_dir: Path | None = None
    lineage: dict = field(default_factory=dict)

    @property
    def pipeline_profile(self) -> str:
        """Canonical profile name; ``prompt_profile`` is kept for compatibility."""

        return self.prompt_profile

    @property
    def input_tokens(self) -> int:
        return self.extraction.input_tokens + self.judgment.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.extraction.output_tokens + self.judgment.output_tokens

    @property
    def credits(self) -> float:
        return self.extraction.credit_usage + self.judgment.credit_usage


def _validate_stage_envelope(
    parsed: dict,
    *,
    stage: str,
    expected_meeting_id: str | None,
) -> tuple[str | None, str | None]:
    collection_field = "items" if stage == "EXTRACTION" else "judgments"
    schema_code = f"INVALID_{stage}_SCHEMA"
    if "meetingId" not in parsed:
        return f"{stage.title()} response is missing meetingId", schema_code
    if (
        expected_meeting_id is not None
        and parsed["meetingId"] != expected_meeting_id
    ):
        return (
            f"{stage.title()} response meetingId does not match the request",
            "MEETING_ID_MISMATCH",
        )
    if collection_field not in parsed:
        return f"{stage.title()} response is missing {collection_field}", schema_code
    values = parsed[collection_field]
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        return (
            f"{stage.title()} response {collection_field} must be an array of objects",
            schema_code,
        )
    return None, None


def _call_stage(
    client: ChatClient,
    prompt: str,
    prompt_sha: str,
    *,
    stage: str,
    expected_meeting_id: str | None,
) -> StageResult:
    """Call one stage and accumulate every parse, schema, and transport attempt."""

    diagnostics: list[dict] = []
    input_tokens = output_tokens = total_tokens = latency_ms = 0
    credit_usage = 0.0
    raw_response = ""
    parsed: dict | None = None
    error: str | None = None
    error_code: str | None = None
    for attempt_index in range(2):
        started = time.perf_counter()
        try:
            response = client.complete([{"role": "user", "content": prompt}])
        except Exception as exc:
            attempt_latency = round((time.perf_counter() - started) * 1000)
            latency_ms += attempt_latency
            error_code = "TRANSPORT_ERROR"
            error = f"LLM transport failed ({type(exc).__name__})"
            diagnostics.append({
                "attempt": attempt_index + 1,
                "success": False,
                "errorCode": error_code,
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
                "creditUsage": 0.0,
                "latencyMs": attempt_latency,
            })
            continue

        raw_response = response.raw_response
        error_code = None
        parsed, error = parse_json_object(raw_response)
        if error is None:
            assert parsed is not None
            error, error_code = _validate_stage_envelope(
                parsed,
                stage=stage,
                expected_meeting_id=expected_meeting_id,
            )
        attempt_credit = estimate_credits(response.input_tokens, response.output_tokens)
        input_tokens += response.input_tokens
        output_tokens += response.output_tokens
        total_tokens += response.total_tokens
        latency_ms += response.latency_ms
        credit_usage += attempt_credit
        if error is None:
            error_code = None
        elif error.startswith("JSON parse error"):
            error_code = "JSON_PARSE_ERROR"
        elif error_code is None:
            error_code = f"INVALID_{stage}_SCHEMA"
        diagnostics.append({
            "attempt": attempt_index + 1,
            "success": error is None,
            "errorCode": error_code,
            "inputTokens": response.input_tokens,
            "outputTokens": response.output_tokens,
            "totalTokens": response.total_tokens,
            "creditUsage": round(attempt_credit, 4),
            "latencyMs": response.latency_ms,
        })
        if error is None:
            break
    return StageResult(
        prompt_sha256=prompt_sha,
        raw_response=raw_response,
        parsed=parsed,
        error=error,
        error_code=error_code,
        attempts=len(diagnostics),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        credit_usage=round(credit_usage, 4),
        attempt_diagnostics=diagnostics,
    )


def _skipped_stage(prompt_sha: str, code: str) -> StageResult:
    return StageResult(
        prompt_sha256=prompt_sha,
        raw_response="",
        parsed=None,
        error=code,
        error_code=code,
        attempts=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        latency_ms=0,
        credit_usage=0.0,
    )


def _request_usage(
    extraction: StageResult,
    judgment: StageResult,
    *,
    previous: dict | None,
    run_attempt: int,
    started_at: datetime,
    status: str,
    failure_stage: str | None,
) -> dict:
    previous = dict(previous or {})
    current_attempts = {
        "extraction": list(extraction.attempt_diagnostics),
        "judgment": list(judgment.attempt_diagnostics),
    }
    current = {
        "runAttempt": run_attempt,
        "startedAt": started_at.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "failureStage": failure_stage,
        "inputTokens": extraction.input_tokens + judgment.input_tokens,
        "outputTokens": extraction.output_tokens + judgment.output_tokens,
        "totalTokens": extraction.total_tokens + judgment.total_tokens,
        "credits": round(extraction.credit_usage + judgment.credit_usage, 4),
        "latencyMs": extraction.latency_ms + judgment.latency_ms,
        "stages": {
            "extraction": {"attempts": current_attempts["extraction"]},
            "judgment": {"attempts": current_attempts["judgment"]},
        },
    }
    previous_runs = list(previous.get("runs") or [])
    previous_attempts = previous.get("attempts") or {}
    return {
        "schemaVersion": "request-usage-v2",
        "inputTokens": int(previous.get("inputTokens") or 0) + current["inputTokens"],
        "outputTokens": int(previous.get("outputTokens") or 0) + current["outputTokens"],
        "totalTokens": int(previous.get("totalTokens") or 0) + current["totalTokens"],
        "credits": round(float(previous.get("credits") or 0) + current["credits"], 4),
        "latencyMs": int(previous.get("latencyMs") or 0) + current["latencyMs"],
        "extractionLatencyMs": (
            int(previous.get("extractionLatencyMs") or 0) + extraction.latency_ms
        ),
        "judgmentLatencyMs": (
            int(previous.get("judgmentLatencyMs") or 0) + judgment.latency_ms
        ),
        "attempts": {
            "extraction": (
                list(previous_attempts.get("extraction") or [])
                + current_attempts["extraction"]
            ),
            "judgment": (
                list(previous_attempts.get("judgment") or [])
                + current_attempts["judgment"]
            ),
        },
        "runs": previous_runs + [current],
    }


def _resolve_adapter(
    profile: PipelineProfile,
    override: JudgmentContractAdapter | None,
) -> JudgmentContractAdapter:
    return override or adapter_for_kind(profile.judgment_adapter_kind)


def run_judgment_only(
    *,
    client: ChatClient,
    items: list[dict],
    segments: list[dict],
    candidates: dict | list | None = None,
    prompt_profile: str | PipelineProfile = DEFAULT_PIPELINE_PROFILE_NAME,
    judgment_adapter: JudgmentContractAdapter | None = None,
    expected_meeting_id: str | None = None,
) -> JudgmentOnlyRunResult:
    """Run stage ② over fixed stage-① artifacts without database mutation.

    This remains a diagnostic primitive.  Production execution should select a
    complete pipeline profile and use :func:`run_generation_only` or
    :func:`run_meeting` so extraction and judgment stay paired.
    """

    profile = get_pipeline_profile(prompt_profile)
    adapter = _resolve_adapter(profile, judgment_adapter)
    prompt = render_judgment_prompt(
        profile,
        items=items,
        candidates=candidates or {"decisions": []},
        segments=segments,
    )
    stage = _call_stage(
        client,
        prompt,
        profile.judgment_asset.sha256,
        stage="JUDGMENT",
        expected_meeting_id=expected_meeting_id,
    )
    raw_judgments = list((stage.parsed or {}).get("judgments") or [])
    adapted = adapter.adapt(items=items, judgments=raw_judgments) if stage.error is None else []
    return JudgmentOnlyRunResult(
        profile_name=profile.name,
        judgment=stage,
        raw_judgments=raw_judgments,
        adapted_judgments=adapted,
        prompt=prompt,
        adapter_version=adapter.version,
    )


def run_generation_only(
    *,
    meeting_input: dict,
    client: ChatClient,
    category_set: CategorySet | None = None,
    prompt_profile: str | PipelineProfile = DEFAULT_PIPELINE_PROFILE_NAME,
    judgment_adapter: JudgmentContractAdapter | None = None,
    term_corrections: list[dict[str, str]] | None = None,
) -> GenerationOnlyRunResult:
    """Run the paired extraction and judgment stages without applying changes."""

    category_config = category_set or CategorySet.load()
    profile = get_pipeline_profile(prompt_profile)
    contract_adapter = _resolve_adapter(profile, judgment_adapter)
    segments = meeting_input.get("segments", [])
    candidates = meeting_input.get("candidates") or {"decisions": []}

    extraction_prompt = render_extraction_prompt(
        profile,
        segments=segments,
        category_values=category_config.values,
        term_corrections=term_corrections,
    )
    extraction = _call_stage(
        client,
        extraction_prompt,
        profile.extraction_asset.sha256,
        stage="EXTRACTION",
        expected_meeting_id=meeting_input["externalMeetingId"],
    )
    parsed_items = (extraction.parsed or {}).get("items") or []
    raw_items = [dict(item) for item in parsed_items if isinstance(item, dict)]
    items = normalize_extraction_items(raw_items)

    if extraction.error is not None:
        return GenerationOnlyRunResult(
            profile_name=profile.name,
            extraction=extraction,
            judgment=_skipped_stage(
                profile.judgment_asset.sha256, "SKIPPED_EXTRACTION_FAILED"
            ),
            raw_items=raw_items,
            items=[],
            raw_judgments=[],
            judgments=[],
            dropped_item_ids=[],
            extraction_prompt=extraction_prompt,
            judgment_prompt="",
            adapter_version=contract_adapter.version,
        )

    judgment_run = run_judgment_only(
        client=client,
        items=items,
        segments=segments,
        candidates=candidates,
        prompt_profile=profile,
        judgment_adapter=contract_adapter,
        expected_meeting_id=meeting_input["externalMeetingId"],
    )
    return GenerationOnlyRunResult(
        profile_name=profile.name,
        extraction=extraction,
        judgment=judgment_run.judgment,
        raw_items=raw_items,
        items=items,
        raw_judgments=judgment_run.raw_judgments,
        judgments=judgment_run.adapted_judgments,
        dropped_item_ids=[],
        extraction_prompt=extraction_prompt,
        judgment_prompt=judgment_run.prompt,
        adapter_version=contract_adapter.version,
    )


def run_meeting(
    session_factory,
    *,
    meeting_input: dict,
    client: ChatClient,
    category_set: CategorySet | None = None,
    pipeline_version: str = NODE_GENERATION_PIPELINE_VERSION,
    output_dir: Path | str | None = None,
    prompt_profile: str | PipelineProfile = DEFAULT_PIPELINE_PROFILE_NAME,
    judgment_adapter: JudgmentContractAdapter | None = None,
    term_corrections: list[dict[str, str]] | None = None,
    force_retry: bool = False,
) -> MeetingRunResult:
    category_config = category_set or CategorySet.load()
    profile = get_pipeline_profile(prompt_profile)
    project_id = meeting_input["projectId"]
    meeting_id = meeting_input["externalMeetingId"]
    request_id = meeting_input.get("requestId", f"req-{meeting_id}")
    segments = meeting_input.get("segments", [])
    candidates = meeting_input.get("candidates") or {"decisions": []}
    client_settings = getattr(client, "settings", None)
    model = getattr(client_settings, "model", "unknown")
    temperature = getattr(client_settings, "temperature", None)
    contract_adapter = _resolve_adapter(profile, judgment_adapter)
    input_hash = generation_input_hash(
        meeting_input=meeting_input,
        pipeline_version=pipeline_version,
        profile=profile,
        category_set=category_config,
        term_corrections=term_corrections,
        adapter_version=contract_adapter.version,
        model=model,
        temperature=temperature,
    )

    lineage_model = Lineage(
        pipelineVersion=pipeline_version,
        extractionPromptName=profile.extraction_asset.name,
        extractionPromptVersion=profile.extraction_asset.version,
        extractionPromptSha256=profile.extraction_asset.sha256,
        judgmentPromptName=profile.judgment_asset.name,
        judgmentPromptVersion=profile.judgment_asset.version,
        judgmentPromptSha256=profile.judgment_asset.sha256,
        promptRendererVersion=profile.renderer_version,
        judgmentContractAdapterVersion=contract_adapter.version,
        model=model,
        categorySchemaVersion=category_config.schema_version,
        generatedBy="AI",
        extra={
            "pipelineProfile": profile.name,
            "profileStatus": profile.status,
            "promptProfile": profile.name,
            "inputHash": input_hash,
            "inputHashVersion": GENERATION_INPUT_HASH_VERSION,
        },
    )
    claim = claim_generation_request(
        session_factory,
        project_id=project_id,
        external_meeting_id=meeting_id,
        external_request_id=request_id,
        pipeline_version=pipeline_version,
        input_hash=input_hash,
        lineage=lineage_model,
        force_retry=force_retry,
    )
    if not claim.claimed:
        assert claim.result is not None
        return MeetingRunResult(
            meeting_id=meeting_id,
            proposal_result=claim.result,
            extraction=_skipped_stage(profile.extraction_asset.sha256, "SKIPPED_PRECLAIM"),
            judgment=_skipped_stage(profile.judgment_asset.sha256, "SKIPPED_PRECLAIM"),
            items=[],
            judgments=[],
            dropped_item_ids=[],
            prompt_profile=profile.name,
            lineage=lineage_model.model_dump(mode="json", exclude_none=True),
        )

    run_started_at = datetime.now(timezone.utc)
    generation = run_generation_only(
        meeting_input=meeting_input,
        client=client,
        category_set=category_config,
        prompt_profile=profile,
        judgment_adapter=contract_adapter,
        term_corrections=term_corrections,
    )

    raw_extraction = (
        generation.extraction.parsed
        if generation.extraction.parsed is not None
        else generation.extraction.raw_response
    )
    raw_judgment = (
        generation.judgment.parsed
        if generation.judgment.parsed is not None
        else generation.judgment.raw_response
    )

    if generation.extraction.error is not None:
        usage = _request_usage(
            generation.extraction,
            generation.judgment,
            previous=claim.previous_usage,
            run_attempt=claim.run_attempt,
            started_at=run_started_at,
            status="FAILED",
            failure_stage="EXTRACTION",
        )
        proposal_result = mark_generation_failed(
            session_factory,
            request_db_id=claim.request_db_id,
            stage="EXTRACTION",
            code=generation.extraction.error_code or "EXTRACTION_FAILED",
            message="Extraction generation failed after retries",
            usage=usage,
            raw_extraction=raw_extraction,
            raw_judgment=None,
            lineage=lineage_model,
        )
        return MeetingRunResult(
            meeting_id=meeting_id,
            proposal_result=proposal_result,
            extraction=generation.extraction,
            judgment=generation.judgment,
            items=[],
            judgments=[],
            dropped_item_ids=[],
            prompt_profile=profile.name,
            lineage=lineage_model.model_dump(mode="json", exclude_none=True),
        )

    warnings: list[str] = []
    warning_stage = warning_code = None
    effective_judgments = generation.judgments
    if generation.judgment.error is not None:
        warnings = ["JUDGMENT_FAILED"]
        warning_stage = "JUDGMENT"
        warning_code = generation.judgment.error_code or "JUDGMENT_FAILED"
        effective_judgments = [
            {
                "itemId": item["id"],
                "result": "MINUTES_ONLY",
                "reason": "JUDGMENT_FAILED",
            }
            for item in generation.items
        ]

    usage = _request_usage(
        generation.extraction,
        generation.judgment,
        previous=claim.previous_usage,
        run_attempt=claim.run_attempt,
        started_at=run_started_at,
        status="REVIEW_PENDING",
        failure_stage=warning_stage,
    )
    payload = {
        "requestId": request_id,
        "projectId": project_id,
        "externalMeetingId": meeting_id,
        "runType": "NODE_GENERATION",
        "pipelineVersion": pipeline_version,
        "segments": segments,
        "items": generation.items,
        "judgments": effective_judgments,
        "candidates": candidates,
    }
    lineage_model.payloadHash = payload_hash(payload)
    try:
        proposal_result = finalize_generation_candidates(
            session_factory,
            payload,
            request_db_id=claim.request_db_id,
            raw_items=generation.raw_items,
            raw_extraction=raw_extraction,
            raw_judgment=raw_judgment,
            lineage=lineage_model,
            usage=usage,
            warnings=warnings,
            warning_failure_stage=warning_stage,
            warning_failure_code=warning_code,
        )
    except Exception:
        logger.exception(
            "candidate persistence failed for request %s", claim.request_db_id
        )
        failed_usage = _request_usage(
            generation.extraction,
            generation.judgment,
            previous=claim.previous_usage,
            run_attempt=claim.run_attempt,
            started_at=run_started_at,
            status="FAILED",
            failure_stage="PERSISTENCE",
        )
        proposal_result = mark_generation_failed(
            session_factory,
            request_db_id=claim.request_db_id,
            stage="PERSISTENCE",
            code="CANDIDATE_PERSISTENCE_FAILED",
            message="Candidate persistence failed",
            usage=failed_usage,
            raw_extraction=raw_extraction,
            raw_judgment=raw_judgment,
            lineage=lineage_model,
        )
    lineage = lineage_model.model_dump(mode="json", exclude_none=True)

    result = MeetingRunResult(
        meeting_id=meeting_id,
        proposal_result=proposal_result,
        extraction=generation.extraction,
        judgment=generation.judgment,
        items=generation.items,
        judgments=effective_judgments,
        dropped_item_ids=generation.dropped_item_ids,
        prompt_profile=profile.name,
        lineage=lineage,
    )

    if output_dir is not None:
        result.output_dir = _write_artifacts(
            Path(output_dir),
            meeting_id,
            result,
            generation.extraction_prompt,
            generation.judgment_prompt,
        )
    return result


def _write_artifacts(
    root: Path,
    meeting_id: str,
    result: MeetingRunResult,
    extraction_prompt: str,
    judgment_prompt: str,
) -> Path:
    out = root / meeting_id
    out.mkdir(parents=True, exist_ok=True)

    def _stage_dump(stage: StageResult) -> dict[str, Any]:
        return {
            "promptSha256": stage.prompt_sha256,
            "attempts": stage.attempts,
            "error": stage.error,
            "errorCode": stage.error_code,
            "inputTokens": stage.input_tokens,
            "outputTokens": stage.output_tokens,
            "totalTokens": stage.total_tokens,
            "latencyMs": stage.latency_ms,
            "creditUsage": stage.credit_usage,
            "attemptDiagnostics": stage.attempt_diagnostics,
            "rawResponse": stage.raw_response,
            "parsed": stage.parsed,
        }

    (out / "extraction.json").write_text(
        json.dumps(_stage_dump(result.extraction), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "judgment.json").write_text(
        json.dumps(_stage_dump(result.judgment), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "extraction_prompt.txt").write_text(extraction_prompt, encoding="utf-8")
    (out / "judgment_prompt.txt").write_text(judgment_prompt, encoding="utf-8")
    (out / "run.json").write_text(
        json.dumps(
            {
                "meetingId": meeting_id,
                "pipelineProfile": result.pipeline_profile,
                "promptProfile": result.prompt_profile,
                "lineage": result.lineage,
                "droppedItemIds": result.dropped_item_ids,
                "credits": round(result.credits, 2),
                "inputTokens": result.input_tokens,
                "outputTokens": result.output_tokens,
                "proposalResult": result.proposal_result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


__all__ = [
    "run_meeting",
    "run_generation_only",
    "run_judgment_only",
    "MeetingRunResult",
    "GenerationOnlyRunResult",
    "JudgmentOnlyRunResult",
    "StageResult",
    "parse_json_object",
    "estimate_credits",
    "generation_input_hash",
    "NODE_GENERATION_PIPELINE_VERSION",
    "M2_PIPELINE_VERSION",
]
