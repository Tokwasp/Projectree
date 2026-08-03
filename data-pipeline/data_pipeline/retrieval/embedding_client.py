"""Real OpenAI-compatible (GMS) embedding adapter.

Implements the existing :class:`EmbeddingClient` port with a live HTTP call.
Offline tests keep using fakes; this module is only constructed when the
operator configures ``EMBEDDING_ADAPTER=gms`` and supplies credentials.

Never logs the API key, the embedded text, or the vector itself.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from .embedding import validate_embedding
from .errors import EmbeddingGenerationError

logger = logging.getLogger(__name__)

#: HTTP statuses worth retrying: transient server and rate-limit conditions.
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class EmbeddingTransportError(EmbeddingGenerationError):
    """Network/HTTP failure that may succeed on a later attempt."""


class EmbeddingResponseError(EmbeddingGenerationError):
    """The provider answered, but the payload is not a usable embedding."""


@dataclass(frozen=True)
class EmbeddingUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    credit: float | None
    source: str


@dataclass(frozen=True)
class EmbeddingCallResult:
    vector: list[float]
    usage: EmbeddingUsage
    latency_ms: int
    request_id: str | None
    retry_count: int
    rate_limit: dict[str, str]


@dataclass(frozen=True)
class EmbeddingClientSettings:
    # repr=False keeps GMS_KEY out of the auto-generated dataclass repr, which
    # would otherwise leak it into tracebacks and any log of these settings.
    api_key: str = field(repr=False)
    base_url: str
    model: str
    dimensions: int
    timeout_seconds: float = 60.0
    retry_count: int = 2
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("GMS_KEY is required for the embedding adapter")
        if not self.base_url:
            raise ValueError("EMBEDDING_BASE_URL/OPENAI_BASE_URL is required")
        if not self.model:
            raise ValueError("RETRIEVAL_EMBEDDING_MODEL is required")
        if self.dimensions <= 0:
            raise ValueError("RETRIEVAL_EMBEDDING_DIM must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("embedding timeout must be positive")
        if self.retry_count < 0:
            raise ValueError("embedding retry count must not be negative")

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/embeddings"


def load_embedding_client_settings() -> EmbeddingClientSettings:
    """Read adapter settings from the environment.

    Falls back to the LLM base URL because GMS exposes one OpenAI-compatible
    gateway for both chat and embeddings.
    """

    from data_pipeline.config import load_settings

    retrieval = load_settings().retrieval
    base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
    return EmbeddingClientSettings(
        api_key=os.getenv("GMS_KEY", ""),
        base_url=base_url,
        model=os.getenv("EMBEDDING_MODEL") or retrieval.embedding_model,
        dimensions=retrieval.embedding_dim,
        timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
        retry_count=int(os.getenv("EMBEDDING_RETRY_COUNT", "2")),
        retry_backoff_seconds=float(
            os.getenv("EMBEDDING_RETRY_BACKOFF_SECONDS", "0.5")
        ),
    )


class GmsEmbeddingClient:
    """OpenAI-compatible ``POST /embeddings`` client."""

    def __init__(
        self,
        settings: EmbeddingClientSettings,
        *,
        transport=None,
        sleep=time.sleep,
    ):
        self.settings = settings
        self._transport = transport
        self._sleep = sleep

    # -- port ------------------------------------------------------------
    def embed(
        self,
        *,
        text: str,
        model: str,
        dimensions: int,
    ) -> Sequence[float]:
        return self.embed_detailed(
            text=text,
            model=model,
            dimensions=dimensions,
        ).vector

    def embed_detailed(
        self,
        *,
        text: str,
        model: str,
        dimensions: int,
    ) -> EmbeddingCallResult:
        if not text.strip():
            raise EmbeddingResponseError("embedding input text must not be blank")
        payload = {
            "model": model or self.settings.model,
            "input": text,
        }
        # text-embedding-3-* accept an explicit output size; older models do not.
        if dimensions:
            payload["dimensions"] = dimensions

        started = time.monotonic()
        data, metadata = self._post_with_retry_detailed(payload)
        vector = self._extract_vector(data)
        validated = validate_embedding(vector, expected_dimension=dimensions)
        return EmbeddingCallResult(
            vector=validated,
            usage=self._extract_usage(data),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            request_id=metadata["request_id"],
            retry_count=metadata["retry_count"],
            rate_limit=metadata["rate_limit"],
        )

    # -- internals -------------------------------------------------------
    def _client(self):
        import httpx

        if self._transport is not None:
            return httpx.Client(
                transport=self._transport,
                timeout=self.settings.timeout_seconds,
            )
        from data_pipeline.provider_safety import assert_external_ai_client_allowed

        assert_external_ai_client_allowed("embedding")
        return httpx.Client(timeout=self.settings.timeout_seconds)

    def _post_with_retry(self, payload: dict) -> dict:
        data, _ = self._post_with_retry_detailed(payload)
        return data

    def _post_with_retry_detailed(self, payload: dict) -> tuple[dict, dict]:
        import httpx

        attempts = self.settings.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with self._client() as client:
                    response = client.post(
                        self.settings.endpoint,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.settings.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
            except httpx.HTTPError as exc:
                last_error = EmbeddingTransportError(
                    f"embedding request failed: {type(exc).__name__}"
                )
            else:
                if response.status_code < 400:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        # A non-JSON 2xx body is a contract violation, not transient.
                        raise EmbeddingResponseError(
                            "embedding response is not valid JSON"
                        ) from exc
                    return data, {
                        "request_id": (
                            response.headers.get("x-request-id")
                            or response.headers.get("request-id")
                        ),
                        "retry_count": attempt - 1,
                        "rate_limit": {
                            key: value
                            for key in (
                                "x-ratelimit-limit-requests",
                                "x-ratelimit-remaining-requests",
                                "x-ratelimit-reset-requests",
                                "retry-after",
                            )
                            if (value := response.headers.get(key)) is not None
                        },
                    }
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    raise EmbeddingTransportError(
                        "embedding request rejected with a non-retryable status "
                        f"{response.status_code}"
                    )
                last_error = EmbeddingTransportError(
                    f"embedding request failed with status {response.status_code}"
                )

            if attempt < attempts:
                logger.warning(
                    "embedding attempt %d/%d failed; retrying", attempt, attempts
                )
                self._sleep(self.settings.retry_backoff_seconds * attempt)

        raise last_error or EmbeddingTransportError("embedding request failed")

    @staticmethod
    def _extract_vector(data: object) -> Sequence[float]:
        if not isinstance(data, dict):
            raise EmbeddingResponseError("embedding response must be a JSON object")
        rows = data.get("data")
        if not isinstance(rows, list) or not rows:
            raise EmbeddingResponseError("embedding response has no data array")
        first = rows[0]
        if not isinstance(first, dict):
            raise EmbeddingResponseError("embedding response item must be an object")
        vector = first.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbeddingResponseError(
                "embedding response item has no embedding array"
            )
        return vector

    @staticmethod
    def _extract_usage(data: object) -> EmbeddingUsage:
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return EmbeddingUsage(None, None, None, None, "UNAVAILABLE")

        def integer(*names: str) -> int | None:
            for name in names:
                value = usage.get(name)
                if isinstance(value, int) and value >= 0:
                    return value
            return None

        input_tokens = integer("input_tokens", "prompt_tokens")
        output_tokens = integer("output_tokens", "completion_tokens")
        total_tokens = integer("total_tokens")
        credit_value = usage.get("credit", usage.get("credits"))
        credit = (
            float(credit_value)
            if isinstance(credit_value, (int, float))
            else None
        )
        source = (
            "PROVIDER_REPORTED"
            if any(
                value is not None
                for value in (
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    credit,
                )
            )
            else "UNAVAILABLE"
        )
        return EmbeddingUsage(
            input_tokens,
            output_tokens,
            total_tokens,
            credit,
            source,
        )


def build_embedding_client(adapter: str | None = None):
    """Select the embedding adapter. Unknown names fail loudly."""

    name = (adapter or os.getenv("EMBEDDING_ADAPTER", "fake")).strip().lower()
    if name in {"gms", "openai"}:
        return GmsEmbeddingClient(load_embedding_client_settings())
    raise ValueError(
        "EMBEDDING_ADAPTER must be 'gms'/'openai' for a real client; "
        f"got {name!r}. Tests inject their own fake explicitly."
    )


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "EmbeddingClientSettings",
    "EmbeddingCallResult",
    "EmbeddingResponseError",
    "EmbeddingTransportError",
    "EmbeddingUsage",
    "GmsEmbeddingClient",
    "build_embedding_client",
    "load_embedding_client_settings",
]
