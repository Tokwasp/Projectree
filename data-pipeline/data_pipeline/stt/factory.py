"""Configuration-driven Transcriber construction."""

from __future__ import annotations

from data_pipeline.config import SttSettings

from .adapters import ClovaTranscriber, FakeTranscriber
from .ports import Transcriber


def build_transcriber(settings: SttSettings) -> Transcriber:
    if settings.adapter == "fake":
        if settings.fake_response_path is not None:
            return FakeTranscriber.from_fixture(settings.fake_response_path)
        return FakeTranscriber()
    if settings.adapter == "clova":
        return ClovaTranscriber(
            invoke_url=settings.clova_invoke_url,
            secret=settings.clova_secret,
            timeout_seconds=settings.clova_timeout_seconds,
        )
    raise ValueError(
        f"Unsupported STT_ADAPTER {settings.adapter!r}; expected fake or clova"
    )


__all__ = ["build_transcriber"]
