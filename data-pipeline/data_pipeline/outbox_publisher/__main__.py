"""Run the Outbox Publisher: python -m data_pipeline.outbox_publisher"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from data_pipeline.config import load_settings
from data_pipeline.jobs.outbox import build_transport_from_env
from data_pipeline.storage import make_engine, make_session_factory

from .runner import OutboxPublisher


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(os.getenv("ENV_FILE", ".env")), override=False)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    engine = make_engine(settings.database_url)
    try:
        session_factory = make_session_factory(engine)
        transport_name = os.getenv("OUTBOX_TRANSPORT", "fake").strip().lower()
        publisher = OutboxPublisher(
            session_factory=session_factory,
            transport=build_transport_from_env(session_factory=session_factory),
            batch_size=int(os.getenv("OUTBOX_BATCH_SIZE", "20")),
            stall_timeout_seconds=float(
                os.getenv("OUTBOX_STALL_TIMEOUT_SECONDS", "300")
            ),
            schema_versions=("3",) if transport_name in {"result-sqs", "sqs"} else None,
        )
        publisher.run_forever(
            idle_sleep_seconds=float(os.getenv("OUTBOX_IDLE_SLEEP_SECONDS", "2"))
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
