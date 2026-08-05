"""Injected port for the B-model judgment stage."""

from __future__ import annotations

from typing import Any, Protocol


class BModelClient(Protocol):
    def recommend(
        self,
        *,
        source_node: dict[str, Any],
        retrieval_candidates: list[dict[str, Any]],
        model: str,
    ) -> object:
        """Return a JSON-compatible decision; external adapters live elsewhere."""


def build_b_model_client(adapter: str | None = None) -> BModelClient:
    """Resolve the configured B-model adapter.

    ``B_MODEL_ADAPTER=gms`` (alias ``openai``) selects the real GMS
    chat-completions adapter. Anything else is a configuration error raised at
    startup so an operator cannot run the Analysis Worker with an unwired B stage.
    """

    import os

    name = (adapter or os.getenv("B_MODEL_ADAPTER", "")).strip().lower()
    if name in {"gms", "openai"}:
        from .gms import GmsBModelClient, load_b_model_client_settings

        return GmsBModelClient(load_b_model_client_settings())
    if not name or name == "none":
        raise RuntimeError(
            "B_MODEL_ADAPTER is not configured. Set B_MODEL_ADAPTER=gms "
            "(with GMS_KEY/OPENAI_BASE_URL or B_MODEL_* overrides), or construct "
            "AnalysisWorker directly with an injected b_model_client."
        )
    raise RuntimeError(
        f"Unknown B_MODEL_ADAPTER {name!r}; supported values: gms, openai."
    )


__all__ = ["BModelClient", "build_b_model_client"]
