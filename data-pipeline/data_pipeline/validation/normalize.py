"""텍스트 정규화 — PoC evidence_evaluator 의 규칙을 수확(재작성).

NFKC 정규화 + 개행 통일 + 공백 접기. STT 원문은 절대 수정하지 않고, 대조 검증에만 쓴다.
"""

from __future__ import annotations

import unicodedata


def normalize_quote(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
