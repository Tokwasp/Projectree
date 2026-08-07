"""Dispatch Java commands after strict subtype parsing."""

from __future__ import annotations

from .contracts import (
    JavaCommandMessage,
    MeetingAnalysisCommandMessage,
    NodeContentUpdateCommandMessage,
)
from .node_updates import process_node_content_update
from .persistence import persist_analysis_command


def dispatch_java_command(session_factory, *, command: JavaCommandMessage):
    if isinstance(command, MeetingAnalysisCommandMessage):
        return persist_analysis_command(session_factory, command=command)
    if isinstance(command, NodeContentUpdateCommandMessage):
        return process_node_content_update(session_factory, command=command)
    raise TypeError(f"unsupported Java command: {type(command).__name__}")


__all__ = ["dispatch_java_command"]
