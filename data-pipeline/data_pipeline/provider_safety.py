"""Process-level emergency brake for real external AI client creation.

``NO_EXTERNAL_AI_CALLS`` remains the default-deny switch.  The only exception
is an explicit, process-local context used by the bounded GMS fatal-smoke CLI.
Environment variables alone cannot open that exception: the CLI must validate
its budgets and enter :func:`gms_fatal_smoke_scope` in the current context.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from collections.abc import Iterator


class ExternalAIProviderBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FatalSmokeAllowance:
    max_http_requests: int
    max_candidate_calls: int
    max_b_model_calls: int
    max_embedding_items: int


_FATAL_SMOKE_ALLOWANCE: ContextVar[FatalSmokeAllowance | None] = ContextVar(
    "gms_fatal_smoke_allowance",
    default=None,
)


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def gms_fatal_smoke_scope(
    *,
    max_http_requests: int,
    max_candidate_calls: int,
    max_b_model_calls: int,
    max_embedding_items: int,
) -> Iterator[FatalSmokeAllowance]:
    """Open the narrow real-provider boundary for the dedicated smoke CLI.

    Both explicit environment flags are required.  Positive, bounded budgets
    are carried in a ContextVar so ordinary workers/tests cannot become enabled
    merely by inheriting environment variables.
    """

    if not _enabled("NO_EXTERNAL_AI_CALLS"):
        raise ExternalAIProviderBlockedError(
            "fatal smoke requires NO_EXTERNAL_AI_CALLS=1"
        )
    if not _enabled("ALLOW_GMS_FATAL_SMOKE"):
        raise ExternalAIProviderBlockedError(
            "fatal smoke requires ALLOW_GMS_FATAL_SMOKE=1"
        )
    limits = (
        max_http_requests,
        max_candidate_calls,
        max_b_model_calls,
        max_embedding_items,
    )
    if any(value <= 0 for value in limits):
        raise ExternalAIProviderBlockedError(
            "fatal smoke budgets must be positive"
        )
    allowance = FatalSmokeAllowance(
        max_http_requests=max_http_requests,
        max_candidate_calls=max_candidate_calls,
        max_b_model_calls=max_b_model_calls,
        max_embedding_items=max_embedding_items,
    )
    token = _FATAL_SMOKE_ALLOWANCE.set(allowance)
    try:
        yield allowance
    finally:
        _FATAL_SMOKE_ALLOWANCE.reset(token)


def assert_external_ai_client_allowed(provider: str) -> None:
    if _enabled("NO_EXTERNAL_AI_CALLS") and _FATAL_SMOKE_ALLOWANCE.get() is None:
        raise ExternalAIProviderBlockedError(
            f"external AI client creation blocked by NO_EXTERNAL_AI_CALLS: {provider}"
        )


__all__ = [
    "ExternalAIProviderBlockedError",
    "FatalSmokeAllowance",
    "assert_external_ai_client_allowed",
    "gms_fatal_smoke_scope",
]
