"""Liveness and readiness."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text

from data_pipeline.api.dependencies import get_session_factory, get_settings
from data_pipeline.api.schemas import HealthResponse
from data_pipeline.config import Settings

router = APIRouter(prefix="/health", tags=["health"])


@lru_cache(maxsize=1)
def _expected_schema_head() -> str:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(root / "data_pipeline" / "storage" / "migrations"),
    )
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Alembic has no current head")
    return head


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok", checks={"process": "ok"})


@router.get("/ready", response_model=HealthResponse)
def ready(
    response: Response,
    settings: Settings = Depends(get_settings),
    session_factory=Depends(get_session_factory),
) -> HealthResponse:
    """Check configuration and DB reachability only.

    Deliberately does NOT call Clova or the LLM: readiness is polled frequently
    and must not spend external quota or inherit provider latency.
    """

    checks: dict[str, str] = {}
    healthy = True

    try:
        checks["config"] = "ok" if settings.database_url else "missing-database-url"
        healthy = healthy and bool(settings.database_url)
    except Exception as exc:
        checks["config"] = f"error: {type(exc).__name__}"
        healthy = False

    try:
        session = session_factory()
        try:
            session.execute(text("SELECT 1"))
            checks["database"] = "ok"
            current_head = session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            expected_head = _expected_schema_head()
            if current_head == expected_head:
                checks["schema"] = "ok"
            else:
                checks["schema"] = (
                    f"outdated: current={current_head or 'none'}, "
                    f"expected={expected_head}"
                )
                healthy = False
        finally:
            session.close()
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)


__all__ = ["router"]
