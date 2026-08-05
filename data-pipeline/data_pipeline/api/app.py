"""FastAPI application factory for the internal graph API.

Every data operation is project-scoped. Production/staging additionally require
the configured service token and must be private-network reachable only.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from .dependencies import dispose_engine, verify_internal_service_token
from .errors import register_exception_handlers
from .middleware import install_http_middleware
from .routers import analysis, candidates, graph, health, meetings

logger = logging.getLogger(__name__)

API_TITLE = "Meeting automatic graph API"
API_VERSION = "2.0.0"

DESCRIPTION = """
Internal HTTP layer over the canonical PostgreSQL graph.

The SQS worker performs the automatic Decision-first graph plan. This API serves
GenerationRun and graph reads plus direct user Node/Relation edits. Legacy
manual MERGE/UNMERGE/REMERGE routes remain compatibility code but are disabled
unless their explicit feature flag is enabled. The API never invokes STT,
Embedding, Retrieval, or an LLM.

Optimistic locking is explicit: mutating calls take `expectedVersion` and answer
**409** with `expectedVersion`/`actualVersion` on conflict.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("review API starting")
    yield
    dispose_engine()
    logger.info("review API stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        dependencies=[Depends(verify_internal_service_token)],
    )
    register_exception_handlers(app)
    install_http_middleware(app)
    app.include_router(health.router)
    app.include_router(meetings.router)
    app.include_router(graph.router)
    app.include_router(graph.internal_router)
    environment = os.getenv("APP_ENV", "local").strip().lower()
    legacy_override = os.getenv("ENABLE_LEGACY_REVIEW_API", "").strip().lower()
    legacy_enabled = (
        legacy_override in {"1", "true", "yes"}
        or (
            legacy_override not in {"0", "false", "no"}
            and environment in {"local", "test", "development", "dev"}
        )
    )
    if legacy_enabled:
        # Compatibility-only. The automatic SQS workflow never calls these
        # approval/reanalysis routes, and production/staging omit them by
        # default while Spring migrates to the graph API.
        app.include_router(candidates.router, deprecated=True)
        app.include_router(analysis.router, deprecated=True)
    return app


app = create_app()

__all__ = ["API_TITLE", "API_VERSION", "app", "create_app"]
