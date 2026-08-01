"""Review REST API (FastAPI). Requires the `api` optional dependency group."""

from .app import API_TITLE, API_VERSION, create_app

__all__ = ["API_TITLE", "API_VERSION", "create_app"]
