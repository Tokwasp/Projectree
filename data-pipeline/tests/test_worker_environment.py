from __future__ import annotations

import os

from data_pipeline.worker.__main__ import load_worker_environment


def test_worker_cli_loads_dotenv_without_overriding_process_env(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / "worker.env"
    env_file.write_text(
        "APP_ENV=test\n"
        "AWS_REGION=ap-northeast-2\n"
        "S3_ALLOWED_BUCKETS=fixture-bucket\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setenv("APP_ENV", "explicit")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("S3_ALLOWED_BUCKETS", raising=False)

    load_worker_environment()

    assert os.environ["APP_ENV"] == "explicit"
    assert os.environ["AWS_REGION"] == "ap-northeast-2"
    assert os.environ["S3_ALLOWED_BUCKETS"] == "fixture-bucket"
