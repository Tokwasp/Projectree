"""Run the Analysis Worker: python -m data_pipeline.analysis_worker"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from data_pipeline.b_model.client import build_b_model_client
from data_pipeline.config import load_settings
from data_pipeline.retrieval.embedding_client import build_embedding_client
from data_pipeline.storage import make_engine, make_session_factory

from .runner import AnalysisWorker


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
        worker = AnalysisWorker(
            session_factory=make_session_factory(engine),
            embedding_client=build_embedding_client(),
            b_model_client=build_b_model_client(),
            b_model_name=os.getenv("B_MODEL_NAME", "b-model"),
            b_model_version=os.getenv("B_MODEL_VERSION", "v1"),
        )
        worker.run_forever(
            idle_sleep_seconds=float(os.getenv("ANALYSIS_IDLE_SLEEP_SECONDS", "2"))
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
