"""Shared FastAPI dependencies: settings, engine, session factory, actor.

The engine and session factory are process-wide singletons. Services own their
own transactions, so routes receive the *factory* and never an open Session.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException, status

from data_pipeline.config import Settings, load_settings
from data_pipeline.storage import make_engine, make_session_factory


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def _engine():
    # make_engine owns pool configuration; the API does not override it so the
    # worker processes and the API keep identical connection behaviour.
    return make_engine(get_settings().database_url)


@lru_cache(maxsize=1)
def get_session_factory():
    return make_session_factory(_engine())


def dispose_engine() -> None:
    """Release pooled connections on shutdown."""

    if _engine.cache_info().currsize:
        _engine().dispose()
    _engine.cache_clear()
    get_session_factory.cache_clear()


def get_project_id(
    x_project_id: str = Header(
        ...,
        alias="X-Project-Id",
        min_length=1,
        max_length=128,
    ),
) -> str:
    """Project scope for every request.

    AUTHENTICATION IS NOT IMPLEMENTED. This header is trusted as-is, so the API
    must stay on an internal network reachable only by Spring. When auth lands,
    this dependency is the single place to derive the project from a verified
    principal instead of a caller-supplied header.
    """

    value = x_project_id.strip()
    if not value:
        # Must match the 422 FastAPI already returns for a MISSING header; a
        # bare ValueError here would surface as a 500 with a stack trace.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Project-Id must not be blank",
        )
    return value


def get_actor_id(
    x_actor_id: str = Header(
        default="api",
        alias="X-Actor-Id",
        max_length=128,
    ),
) -> str:
    return x_actor_id.strip() or "api"


__all__ = [
    "dispose_engine",
    "get_actor_id",
    "get_project_id",
    "get_session_factory",
    "get_settings",
]
