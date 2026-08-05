"""Row claiming shared by the analysis worker and the outbox publisher.

PostgreSQL uses ``FOR UPDATE SKIP LOCKED`` so several workers can drain the same
table without blocking each other. SQLite ignores ``FOR UPDATE`` entirely, so the
test harness falls back to a plain locked read; that is safe because the SQLite
path is single-writer by construction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Cap so repeated failures cannot push the next attempt years into the future.
MAX_BACKOFF_SECONDS = 3600.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def backoff_delay(attempt_count: int, *, base_seconds: float = 2.0) -> timedelta:
    """Exponential backoff on the number of attempts already made."""

    if attempt_count < 1:
        return timedelta(seconds=0)
    seconds = min(base_seconds * (2 ** (attempt_count - 1)), MAX_BACKOFF_SECONDS)
    return timedelta(seconds=seconds)


def supports_skip_locked(session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def claim_rows(session, statement, *, limit: int):
    """Select claimable rows, skipping ones another worker already holds."""

    if supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)
    statement = statement.limit(limit)
    return list(session.execute(statement).scalars().all())


__all__ = [
    "MAX_BACKOFF_SECONDS",
    "as_utc",
    "backoff_delay",
    "claim_rows",
    "supports_skip_locked",
    "utcnow",
]
