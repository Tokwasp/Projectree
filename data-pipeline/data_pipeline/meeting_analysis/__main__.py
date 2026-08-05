"""Run one v3 component: python -m data_pipeline.meeting_analysis <role>."""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from .runtime import (
    build_command_consumer_runtime,
    build_coordinator_runtime,
    build_recording_consumer_runtime,
)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(os.getenv("ENV_FILE", ".env")), override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "role",
        choices=("recording-ready-consumer", "analysis-command-consumer", "coordinator"),
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    builder = {
        "recording-ready-consumer": build_recording_consumer_runtime,
        "analysis-command-consumer": build_command_consumer_runtime,
        "coordinator": build_coordinator_runtime,
    }[args.role]
    runtime = builder()
    try:
        if args.role != "coordinator":
            runtime.component.run_forever()
            return
        interval = float(os.getenv("ANALYSIS_COORDINATOR_IDLE_SECONDS", "2"))
        while True:
            result = runtime.component.run_once()
            if not result.claimed:
                time.sleep(interval)
    except KeyboardInterrupt:
        return
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
