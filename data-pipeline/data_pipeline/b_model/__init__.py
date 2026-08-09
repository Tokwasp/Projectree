"""B-model ports; no external provider adapter is bundled.

Failure classification lives in the dependency-free ``.failures`` module and is
re-exported here, so pipeline code can map an exception onto a stable
``b_model_failure_code`` without importing a concrete provider adapter.
"""

from .client import BModelClient
from .failures import (
    FAILURE_HTTP_ERROR,
    FAILURE_INVALID_RESPONSE,
    FAILURE_TIMEOUT,
    FAILURE_TRANSPORT_ERROR,
    FAILURE_UNCLASSIFIED,
    FAILURE_VALIDATION_ERROR,
    MAX_PROVIDER_MESSAGE_CHARS,
    describe_b_model_failure,
    redact_secrets,
    sanitize_text,
)

__all__ = [
    "BModelClient",
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
