"""Application service for deterministic STT text normalization."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .contracts import (
    NormalizationChange,
    NormalizationResult,
    TermDictionary,
)
from .dictionary import (
    calculate_dictionary_sha256,
    load_term_dictionary,
)
from .rules import (
    NormalizationRule,
    RuleMatch,
    build_normalization_rules,
    find_rule_matches,
)

MAX_INPUT_TEXT_LENGTH = 100_000
MAX_NORMALIZED_TEXT_LENGTH = 100_000


@dataclass(frozen=True, slots=True)
class _NormalizedInput:
    text: str
    original_spans: tuple[tuple[int, int], ...] | None

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if self.original_spans is None:
            return start, end

        spans = self.original_spans[start:end]
        if not spans:
            raise ValueError("normalization match must not be empty")
        return min(span[0] for span in spans), max(span[1] for span in spans)


def _replacement_span(
    original_start: int,
    original_end: int,
    normalized_offset: int,
    normalized_length: int,
) -> tuple[int, int]:
    original_length = original_end - original_start
    if original_length == 0:
        return original_start, original_start

    start = (
        original_start
        + normalized_offset * original_length // normalized_length
    )
    end_numerator = (normalized_offset + 1) * original_length
    end = original_start + (
        end_numerator + normalized_length - 1
    ) // normalized_length
    return start, end


def _normalize_nfkc_with_offsets(
    text: str,
    *,
    max_normalized_text_length: int,
) -> _NormalizedInput:
    normalized = unicodedata.normalize("NFKC", text)
    if len(normalized) > max_normalized_text_length:
        raise ValueError(
            "normalized text exceeds max_normalized_text_length: "
            f"{len(normalized)} > {max_normalized_text_length}"
        )

    if normalized == text:
        return _NormalizedInput(
            text=text,
            original_spans=None,
        )

    spans: list[tuple[int, int] | None] = [None] * len(normalized)
    matcher = SequenceMatcher(
        a=text,
        b=normalized,
        autojunk=False,
    )

    for tag, original_start, original_end, normalized_start, normalized_end in (
        matcher.get_opcodes()
    ):
        if tag == "equal":
            for offset in range(normalized_end - normalized_start):
                spans[normalized_start + offset] = (
                    original_start + offset,
                    original_start + offset + 1,
                )
            continue

        if tag == "delete":
            continue

        normalized_length = normalized_end - normalized_start
        for offset in range(normalized_length):
            spans[normalized_start + offset] = _replacement_span(
                original_start,
                original_end,
                offset,
                normalized_length,
            )

    if any(span is None for span in spans):
        raise RuntimeError("failed to build NFKC offset mapping")

    return _NormalizedInput(
        text=normalized,
        original_spans=tuple(
            span for span in spans if span is not None
        ),
    )


@dataclass(frozen=True, slots=True)
class _AppliedMatch:
    match: RuleMatch
    normalized_start: int
    normalized_end: int


def _replace_matches(
    text: str,
    matches: tuple[RuleMatch, ...],
) -> tuple[str, tuple[_AppliedMatch, ...]]:
    if not matches:
        return text, ()

    parts: list[str] = []
    applied_matches: list[_AppliedMatch] = []
    cursor = 0
    normalized_position = 0

    for match in matches:
        unchanged = text[cursor : match.start]
        parts.append(unchanged)
        normalized_position += len(unchanged)

        normalized_start = normalized_position
        parts.append(match.rule.canonical)
        normalized_position += len(match.rule.canonical)
        applied_matches.append(
            _AppliedMatch(
                match=match,
                normalized_start=normalized_start,
                normalized_end=normalized_position,
            )
        )
        cursor = match.end

    parts.append(text[cursor:])
    return "".join(parts), tuple(applied_matches)


class SttNormalizationService:
    """Load and compile a dictionary once, then normalize many STT texts."""

    def __init__(
        self,
        dictionary: TermDictionary,
        *,
        max_input_text_length: int = MAX_INPUT_TEXT_LENGTH,
        max_normalized_text_length: int = MAX_NORMALIZED_TEXT_LENGTH,
    ) -> None:
        if max_input_text_length < 1:
            raise ValueError("max_input_text_length must be positive")
        if max_normalized_text_length < 1:
            raise ValueError(
                "max_normalized_text_length must be positive"
            )

        self._dictionary = dictionary
        self._dictionary_sha256 = calculate_dictionary_sha256(dictionary)
        self._rules: tuple[NormalizationRule, ...] = (
            build_normalization_rules(dictionary)
        )
        self._max_input_text_length = max_input_text_length
        self._max_normalized_text_length = max_normalized_text_length

    @classmethod
    def from_dictionary_file(
        cls,
        path: str | Path | None = None,
        *,
        max_input_text_length: int = MAX_INPUT_TEXT_LENGTH,
        max_normalized_text_length: int = MAX_NORMALIZED_TEXT_LENGTH,
    ) -> "SttNormalizationService":
        return cls(
            load_term_dictionary(path),
            max_input_text_length=max_input_text_length,
            max_normalized_text_length=max_normalized_text_length,
        )

    @property
    def dictionary_version(self) -> str:
        return self._dictionary.dictionary_version

    @property
    def dictionary_sha256(self) -> str:
        return self._dictionary_sha256

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def normalize(self, text: str) -> NormalizationResult:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if len(text) > self._max_input_text_length:
            raise ValueError(
                "text exceeds max_input_text_length: "
                f"{len(text)} > {self._max_input_text_length}"
            )

        normalized_input = _normalize_nfkc_with_offsets(
            text,
            max_normalized_text_length=self._max_normalized_text_length,
        )
        matches = find_rule_matches(normalized_input.text, self._rules)
        normalized_text, applied_matches = _replace_matches(
            normalized_input.text,
            matches,
        )
        changes = [
            self._build_change(text, normalized_input, applied_match)
            for applied_match in applied_matches
        ]

        return NormalizationResult(
            dictionary_version=self.dictionary_version,
            dictionary_sha256=self.dictionary_sha256,
            unicode_normalized=normalized_input.text != text,
            original_text=text,
            normalized_text=normalized_text,
            changes=changes,
        )

    @staticmethod
    def _build_change(
        original_text: str,
        normalized_input: _NormalizedInput,
        applied_match: _AppliedMatch,
    ) -> NormalizationChange:
        match = applied_match.match
        original_start, original_end = normalized_input.original_span(
            match.start,
            match.end,
        )
        return NormalizationChange(
            term_id=match.rule.term_id,
            variant=match.rule.variant,
            original=original_text[original_start:original_end],
            matched_text=match.original,
            canonical=match.rule.canonical,
            original_start=original_start,
            original_end=original_end,
            normalized_start=applied_match.normalized_start,
            normalized_end=applied_match.normalized_end,
        )


@lru_cache(maxsize=1)
def get_default_normalization_service() -> SttNormalizationService:
    """Return the process-wide default service with precompiled rules."""

    return SttNormalizationService.from_dictionary_file()


def initialize_default_normalization_service() -> SttNormalizationService:
    """Validate and compile the default dictionary during application startup."""

    return get_default_normalization_service()


__all__ = [
    "MAX_INPUT_TEXT_LENGTH",
    "MAX_NORMALIZED_TEXT_LENGTH",
    "SttNormalizationService",
    "get_default_normalization_service",
    "initialize_default_normalization_service",
]
