"""Deterministic STT text normalization."""

from .contracts import (
    MatchMode,
    NormalizationChange,
    NormalizationResult,
    TermDictionary,
    TermEntry,
)
from .dictionary import (
    DEFAULT_TERM_DICTIONARY_PATH,
    calculate_dictionary_sha256,
    load_term_dictionary,
)
from .rules import (
    NormalizationRule,
    RuleMatch,
    apply_normalization_rules,
    build_normalization_rules,
    find_rule_matches,
)
from .service import (
    MAX_INPUT_TEXT_LENGTH,
    MAX_NORMALIZED_TEXT_LENGTH,
    SttNormalizationService,
    get_default_normalization_service,
    initialize_default_normalization_service,
)

__all__ = [
    "DEFAULT_TERM_DICTIONARY_PATH",
    "MAX_INPUT_TEXT_LENGTH",
    "MAX_NORMALIZED_TEXT_LENGTH",
    "MatchMode",
    "NormalizationChange",
    "NormalizationRule",
    "NormalizationResult",
    "RuleMatch",
    "SttNormalizationService",
    "TermDictionary",
    "TermEntry",
    "apply_normalization_rules",
    "build_normalization_rules",
    "calculate_dictionary_sha256",
    "find_rule_matches",
    "get_default_normalization_service",
    "initialize_default_normalization_service",
    "load_term_dictionary",
]
