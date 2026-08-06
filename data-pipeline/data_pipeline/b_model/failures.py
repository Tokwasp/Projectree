"""Stable failure codes and message sanitising for the B-model stage.

Kept dependency-free (and separate from the GMS adapter) so pipeline code can
classify a B-model exception without importing a concrete provider client or
paying the prompt-registry import cost.

A failure code answers "why did the call not produce a decision", and is what
lands in ``node_analysis_run.b_model_failure_code``. Keep the set small:
operators grep for these strings.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

#: The provider answered with a >=400 status (400/401/403/404/429/5xx).
FAILURE_HTTP_ERROR = "B_MODEL_HTTP_ERROR"
#: The request timed out before any response.
FAILURE_TIMEOUT = "B_MODEL_TIMEOUT"
#: Connection or protocol failure reaching the provider.
FAILURE_TRANSPORT_ERROR = "B_MODEL_TRANSPORT_ERROR"
#: 2xx, but the body was not a usable decision object.
FAILURE_INVALID_RESPONSE = "B_MODEL_INVALID_RESPONSE"
#: A decision was returned but violated the ``BModelDecision`` contract.
FAILURE_VALIDATION_ERROR = "B_MODEL_VALIDATION_ERROR"
#: We could not attribute the failure. Deliberately NOT folded into
#: ``FAILURE_TRANSPORT_ERROR``: a local ``AttributeError`` must not send an
#: operator to look at the network.
FAILURE_UNCLASSIFIED = "B_MODEL_UNCLASSIFIED_ERROR"

#: Upper bound on provider-supplied text we persist or log. GMS answers some
#: failures with a full HTML error page; that must never reach the database.
MAX_PROVIDER_MESSAGE_CHARS = 500

#: Credential shapes that can appear in text a provider echoes back to us.
#: Provider error bodies are arbitrary remote text - some gateways include the
#: offending request - so redaction happens before anything is persisted.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\b(api[-_]?key|authorization|token|secret)\b\s*[:=]\s*\S+"),
)


def redact_secrets(value: str) -> str:
    """Blank out credential-shaped substrings."""

    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def sanitize_text(value: str) -> str:
    """Redact credentials, flatten whitespace, and cap length for logs and DB."""

    cleaned = " ".join(redact_secrets(value).split())
    if len(cleaned) > MAX_PROVIDER_MESSAGE_CHARS:
        cleaned = cleaned[:MAX_PROVIDER_MESSAGE_CHARS] + "...(truncated)"
    return cleaned


def describe_b_model_failure(exc: BaseException) -> tuple[str, str]:
    """Map a B-model exception onto a stable ``(failure_code, message)`` pair.

    Adapters attach their own ``failure_code``; anything else is classified
    here. The message is sanitized once, at this boundary, so no call site has
    to remember to do it before persisting.
    """

    failure_code = getattr(exc, "failure_code", None)
    if not isinstance(failure_code, str) or not failure_code:
        failure_code = (
            FAILURE_VALIDATION_ERROR
            if isinstance(exc, ValidationError)
            else FAILURE_UNCLASSIFIED
        )

    # An adapter that already extracted the provider's own explanation has
    # capped it; re-capping the composed string would truncate a long body a
    # second time and throw the actual cause away.
    provider_message = getattr(exc, "provider_message", None)
    if isinstance(provider_message, str) and provider_message:
        return failure_code, redact_secrets(
            f"{type(exc).__name__}: {exc}"
        )
    return failure_code, sanitize_text(f"{type(exc).__name__}: {exc}")


__all__ = [
    "FAILURE_HTTP_ERROR",
    "FAILURE_INVALID_RESPONSE",
    "FAILURE_TIMEOUT",
    "FAILURE_TRANSPORT_ERROR",
    "FAILURE_UNCLASSIFIED",
    "FAILURE_VALIDATION_ERROR",
    "MAX_PROVIDER_MESSAGE_CHARS",
    "describe_b_model_failure",
    "redact_secrets",
    "sanitize_text",
]
