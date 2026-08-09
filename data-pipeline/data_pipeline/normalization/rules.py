"""Deterministic matching and replacement rules for STT terms."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from .contracts import MatchMode, TermDictionary

_ASCII_WORD_CHARACTER = r"A-Za-z0-9_"
_HANGUL_CHARACTER = "가-힣"
_WORD_CHARACTER = f"{_ASCII_WORD_CHARACTER}{_HANGUL_CHARACTER}"
_KOREAN_PARTICLE_BASES = (
    "으로부터",
    "로부터",
    "에게서",
    "한테서",
    "에서",
    "에게",
    "한테",
    "께서",
    "으로서",
    "으로써",
    "으로",
    "부터",
    "까지",
    "처럼",
    "보다",
    "하고",
    "와",
    "과",
    "로",
    "에",
    "께",
    "의",
    "랑",
)
_KOREAN_PARTICLE_AUXILIARIES = ("은", "는", "도", "만")
_KOREAN_PARTICLES = tuple(
    sorted(
        {
            *_KOREAN_PARTICLE_BASES,
            *(
                base + auxiliary
                for base in _KOREAN_PARTICLE_BASES
                for auxiliary in _KOREAN_PARTICLE_AUXILIARIES
            ),
            *_KOREAN_PARTICLE_AUXILIARIES,
            "이",
            "가",
            "을",
            "를",
        },
        key=lambda particle: (-len(particle), particle),
    )
)
_KOREAN_PARTICLE_PATTERN = "|".join(
    re.escape(particle) for particle in _KOREAN_PARTICLES
)


@dataclass(frozen=True, slots=True)
class NormalizationRule:
    """A compiled variant-to-canonical replacement rule."""

    term_id: str
    variant: str
    canonical: str
    match_mode: MatchMode
    case_sensitive: bool
    pattern: re.Pattern[str] = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """A non-overlapping rule match found in the original text."""

    rule: NormalizationRule
    start: int
    end: int
    original: str


def _is_ascii_word_character(character: str) -> bool:
    return character.isascii() and (character.isalnum() or character == "_")


def _is_hangul_character(character: str) -> bool:
    return "가" <= character <= "힣"


def _variant_key(variant: str) -> str:
    return unicodedata.normalize("NFKC", variant).strip().casefold()


def _escape_with_flexible_whitespace(variant: str) -> str:
    return "".join(
        r"[ \t]+" if part.isspace() else re.escape(part)
        for part in re.split(r"(\s+)", variant)
        if part
    )


def _compile_variant_pattern(
    variant: str,
    *,
    match_mode: MatchMode,
    case_sensitive: bool,
) -> re.Pattern[str]:
    if not variant or not variant.strip():
        raise ValueError("variant must not be empty")

    escaped = _escape_with_flexible_whitespace(variant)
    prefix = ""
    suffix = ""

    if match_mode == "word":
        if _is_ascii_word_character(variant[0]) or _is_hangul_character(
            variant[0]
        ):
            prefix = rf"(?<![{_WORD_CHARACTER}])"

        if _is_ascii_word_character(variant[-1]):
            suffix = rf"(?![{_ASCII_WORD_CHARACTER}])"
        elif _is_hangul_character(variant[-1]):
            suffix = (
                rf"(?=$|[^{_WORD_CHARACTER}]|"
                rf"(?:{_KOREAN_PARTICLE_PATTERN})"
                rf"(?=$|[^{_WORD_CHARACTER}]))"
            )

    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(f"{prefix}{escaped}{suffix}", flags=flags)


def build_normalization_rules(
    dictionary: TermDictionary,
) -> tuple[NormalizationRule, ...]:
    """Build enabled rules, ordered longest variant first."""

    rules: list[NormalizationRule] = []
    variant_owners: dict[str, str] = {}

    for term in dictionary.terms:
        if not term.enabled:
            continue

        if unicodedata.normalize("NFKC", term.canonical) != term.canonical:
            raise ValueError(
                f"canonical must be NFKC-normalized: {term.id}"
            )

        for variant in term.variants:
            if unicodedata.normalize("NFKC", variant) != variant:
                raise ValueError(
                    f"variant must be NFKC-normalized: {variant!r}"
                )

            variant_key = _variant_key(variant)
            if variant_key in variant_owners:
                owner = variant_owners[variant_key]
                raise ValueError(
                    "duplicate normalization variant: "
                    f"{variant!r} ({owner}, {term.id})"
                )
            variant_owners[variant_key] = term.id

            rules.append(
                NormalizationRule(
                    term_id=term.id,
                    variant=variant,
                    canonical=term.canonical,
                    match_mode=term.match_mode,
                    case_sensitive=term.case_sensitive,
                    pattern=_compile_variant_pattern(
                        variant,
                        match_mode=term.match_mode,
                        case_sensitive=term.case_sensitive,
                    ),
                )
            )

    rules.sort(
        key=lambda rule: (
            -len(rule.variant),
            rule.term_id,
            rule.variant.casefold(),
        )
    )
    return tuple(rules)


def find_rule_matches(
    text: str,
    rules: Iterable[NormalizationRule],
) -> tuple[RuleMatch, ...]:
    """Find leftmost, longest, non-overlapping matches in the original text."""

    candidates: list[tuple[int, int, int, re.Match[str], NormalizationRule]] = []

    for priority, rule in enumerate(rules):
        for match in rule.pattern.finditer(text):
            if match.group(0) == rule.canonical:
                continue

            candidates.append(
                (
                    match.start(),
                    -(match.end() - match.start()),
                    priority,
                    match,
                    rule,
                )
            )

    candidates.sort(key=lambda candidate: candidate[:3])

    selected: list[RuleMatch] = []
    occupied_until = 0

    for _, _, _, match, rule in candidates:
        if match.start() < occupied_until:
            continue

        selected.append(
            RuleMatch(
                rule=rule,
                start=match.start(),
                end=match.end(),
                original=match.group(0),
            )
        )
        occupied_until = match.end()

    return tuple(selected)


def apply_normalization_rules(
    text: str,
    rules: Iterable[NormalizationRule],
) -> str:
    """Apply rules once without reprocessing replacement output."""

    matches = find_rule_matches(text, rules)
    if not matches:
        return text

    parts: list[str] = []
    cursor = 0

    for match in matches:
        parts.append(text[cursor : match.start])
        parts.append(match.rule.canonical)
        cursor = match.end

    parts.append(text[cursor:])
    return "".join(parts)


__all__ = [
    "NormalizationRule",
    "RuleMatch",
    "apply_normalization_rules",
    "build_normalization_rules",
    "find_rule_matches",
]
