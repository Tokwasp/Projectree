"""Run the review API: python -m data_pipeline.api"""

from __future__ import annotations

import logging
import os
from pathlib import Path


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(os.getenv("ENV_FILE", ".env")), override=False)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    import uvicorn

    uvicorn.run(
        "data_pipeline.api.app:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "").lower() in {"1", "true", "yes"},
        # Give in-flight review requests time to finish before the socket closes.
        timeout_graceful_shutdown=int(
            os.getenv("API_GRACEFUL_SHUTDOWN_SECONDS", "20")
        ),
    )


if __name__ == "__main__":
    main()
