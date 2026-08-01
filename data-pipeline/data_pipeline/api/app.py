"""FastAPI application factory for the review API.

INTERNAL SERVICE. There is no authentication yet: every request is trusted and
scoped by the X-Project-Id header. Deploy it on a private network reachable only
by Spring, and add auth at data_pipeline/api/dependencies.get_project_id.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .dependencies import dispose_engine
from .errors import register_exception_handlers
from .middleware import install_http_middleware
from .routers import analysis, candidates, health, meetings

logger = logging.getLogger(__name__)

API_TITLE = "Meeting pipeline review API"
API_VERSION = "1.0.0"

DESCRIPTION = """
Thin HTTP layer over the meeting pipeline's existing review services.

Long-running analysis (embedding, pgvector Retrieval, B model) is never executed
inside a request: completing initial review returns **202 Accepted** and a
durable `analysis_job` row that the Analysis Worker drains.

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
    )
    register_exception_handlers(app)
    install_http_middleware(app)
    app.include_router(health.router)
    app.include_router(meetings.router)
    app.include_router(candidates.router)
    app.include_router(analysis.router)
    return app


app = create_app()

__all__ = ["API_TITLE", "API_VERSION", "app", "create_app"]
