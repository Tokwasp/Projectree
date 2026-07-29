"""LLM 어댑터 (GMS OpenAI 호환).

- 인증과 연결 정보는 GMS_KEY, OPENAI_BASE_URL 환경변수로만 받는다.
- json_object 모드(자유 JSON) — 파싱/검증은 파이썬(validation)에서.
- timeout 180s, retry 2 (SDK 자동 재시도). 키는 .env 로만 주입(커밋 금지).
- M1/오프라인 테스트는 이 모듈을 import 하지 않는다(openai 미설치여도 무방).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

@dataclass(frozen=True)
class LLMResponse:
    raw_response: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> LLMResponse: ...


@dataclass(frozen=True)
class LLMSettings:
    gms_key: str
    openai_base_url: str
    model: str
    temperature: float | None = 0.0
    max_output_tokens: int | None = None
    timeout_seconds: float = 180.0
    retry_count: int = 2


def load_llm_settings(*, env_file: str | Path | None = None, require_api_key: bool = True) -> LLMSettings:
    if env_file is not None:
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:
            pass
    gms_key = os.getenv("GMS_KEY", "")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "")
    if require_api_key and not gms_key:
        raise RuntimeError("GMS_KEY is required")
    if not openai_base_url:
        raise RuntimeError("OPENAI_BASE_URL is required")
    if not model:
        raise RuntimeError("OPENAI_MODEL is required")
    temp_raw = os.getenv("OPENAI_TEMPERATURE")
    temperature: float | None = 0.0
    if temp_raw is not None and temp_raw != "":
        temperature = None if temp_raw.lower() == "none" else float(temp_raw)
    return LLMSettings(
        gms_key=gms_key,
        openai_base_url=openai_base_url,
        model=model,
        temperature=temperature,
        max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS")) if os.getenv("OPENAI_MAX_OUTPUT_TOKENS") else None,
        timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "180")),
        retry_count=int(os.getenv("OPENAI_RETRY_COUNT", "2")),
    )


class OpenAIChatClient:
    """GMS OpenAI 호환 채팅 클라이언트. json_object 강제."""

    def __init__(self, settings: LLMSettings) -> None:
        if not settings.gms_key:
            raise RuntimeError("GMS_KEY is required")
        if not settings.openai_base_url:
            raise RuntimeError("OPENAI_BASE_URL is required")
        if not settings.model:
            raise RuntimeError("OPENAI_MODEL is required")
        from openai import OpenAI

        self.settings = settings
        self._client = OpenAI(
            api_key=settings.gms_key, base_url=settings.openai_base_url,
            timeout=settings.timeout_seconds, max_retries=settings.retry_count,
        )

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        req: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if self.settings.temperature is not None:
            req["temperature"] = self.settings.temperature
        if self.settings.max_output_tokens is not None:
            req["max_tokens"] = self.settings.max_output_tokens
        started = time.perf_counter()
        resp = self._client.chat.completions.create(**req)
        latency_ms = round((time.perf_counter() - started) * 1000)
        raw = resp.choices[0].message.content or ""
        if not raw:
            raise RuntimeError("모델이 빈 응답을 반환했습니다.")
        u = resp.usage
        return LLMResponse(
            raw_response=raw,
            input_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(u, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(u, "total_tokens", 0) or 0),
            latency_ms=latency_ms,
        )


__all__ = ["LLMResponse", "ChatClient", "LLMSettings", "load_llm_settings", "OpenAIChatClient"]
