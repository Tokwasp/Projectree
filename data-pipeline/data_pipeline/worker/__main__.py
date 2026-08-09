"""Run the single-concurrency SQS audio worker."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .runtime import build_worker_runtime


def load_worker_environment() -> None:
    """Load local settings without overriding explicit process environment."""

    from dotenv import load_dotenv

    load_dotenv(Path(os.getenv("ENV_FILE", ".env")), override=False)


def main() -> None:
    load_worker_environment()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    runtime = build_worker_runtime()
    try:
        runtime.worker.run_forever()
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
