from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from data_pipeline.llm import LLMSettings, OpenAIChatClient, load_llm_settings


@pytest.fixture(autouse=True)
def clear_llm_environment(monkeypatch):
    for name in ("GMS_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_TEMPERATURE"):
        monkeypatch.delenv(name, raising=False)


def test_loads_gms_environment_from_requested_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GMS_KEY=test-gms-key\n"
        "OPENAI_BASE_URL=https://gms.example/v1\n"
        "OPENAI_MODEL=gpt-test\n"
        "OPENAI_TEMPERATURE=0.25\n",
        encoding="utf-8",
    )

    settings = load_llm_settings(env_file=env_file)

    assert settings.gms_key == "test-gms-key"
    assert settings.openai_base_url == "https://gms.example/v1"
    assert settings.model == "gpt-test"
    assert settings.temperature == 0.25


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"OPENAI_BASE_URL": "https://gms.example/v1", "OPENAI_MODEL": "gpt-test"}, "GMS_KEY is required"),
        ({"GMS_KEY": "key", "OPENAI_MODEL": "gpt-test"}, "OPENAI_BASE_URL is required"),
        ({"GMS_KEY": "key", "OPENAI_BASE_URL": "https://gms.example/v1"}, "OPENAI_MODEL is required"),
    ],
)
def test_required_gms_values_raise_clear_errors(monkeypatch, environment, message):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=f"^{message}$"):
        load_llm_settings()


def test_openai_client_receives_gms_key_and_base_url(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    settings = LLMSettings(
        gms_key="test-gms-key",
        openai_base_url="https://gms.example/v1",
        model="gpt-test",
    )

    OpenAIChatClient(settings)

    assert captured["api_key"] == "test-gms-key"
    assert captured["base_url"] == "https://gms.example/v1"
