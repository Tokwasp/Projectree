"""Versioned STT term dictionary loader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import TermDictionary

DEFAULT_TERM_DICTIONARY_PATH = Path(__file__).resolve().parent / "stt_terms.json"


def load_term_dictionary(path: str | Path | None = None) -> TermDictionary:
    """Read a JSON term dictionary and validate it against its contract."""

    dictionary_path = Path(path) if path is not None else DEFAULT_TERM_DICTIONARY_PATH
    raw_json = dictionary_path.read_text(encoding="utf-8")
    return TermDictionary.model_validate_json(raw_json)


def calculate_dictionary_sha256(dictionary: TermDictionary) -> str:
    """Hash validated dictionary content independently of JSON formatting."""

    canonical_json = json.dumps(
        dictionary.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_TERM_DICTIONARY_PATH",
    "calculate_dictionary_sha256",
    "load_term_dictionary",
]
