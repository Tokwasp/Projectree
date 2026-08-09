"""Environment-safe meeting-summary adapter assembly."""

from __future__ import annotations

from data_pipeline.llm import ChatClient, OpenAIChatClient, load_llm_settings

from .contracts import MeetingSummaryGenerator
from .fake import FakeMeetingSummaryGenerator
from .gms import GmsMeetingSummaryGenerator


LOCAL_ENVIRONMENTS = frozenset({"test", "local", "development", "dev"})


def build_meeting_summary_generator(
    adapter: str,
    *,
    app_env: str,
    chat_client: ChatClient | None = None,
) -> MeetingSummaryGenerator:
    """Build Fake only for local/test and a real GMS adapter otherwise."""

    name = adapter.strip().lower()
    environment = app_env.strip().lower()
    if name == "fake":
        if environment not in LOCAL_ENVIRONMENTS:
            raise RuntimeError(
                "SUMMARY_ADAPTER=fake is forbidden outside local/test"
            )
        return FakeMeetingSummaryGenerator()
    if name in {"gms", "openai"}:
        return GmsMeetingSummaryGenerator(
            chat_client or OpenAIChatClient(load_llm_settings())
        )
    raise ValueError("SUMMARY_ADAPTER must be fake, gms, or openai")


__all__ = ["LOCAL_ENVIRONMENTS", "build_meeting_summary_generator"]
