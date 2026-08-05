"""validation — PoC v3 서버 하드 검증 규칙을 v2.2 계약으로 재작성한 것 (규칙 1~8 생성부).

규칙 7(기술적 중복 실적용)·8(원자 적용)·9(optimistic lock)의 DB 실행은 pipeline.apply 에 있다.
"""

from __future__ import annotations

from .evidence import (
    MIN_QUOTE_CHARS,
    EvidenceResolution,
    ResolvedEvidence,
    SegmentInfo,
    resolve_item_evidence,
)
from .judgments import ValidationResult, field_violations, validate_judgments
from .normalize import normalize_quote
from .plan import (
    build_change_plan,
    source_key,
    title_evidence_signature,
)

__all__ = [
    "normalize_quote",
    "MIN_QUOTE_CHARS", "SegmentInfo", "ResolvedEvidence", "EvidenceResolution", "resolve_item_evidence",
    "ValidationResult", "validate_judgments", "field_violations",
    "build_change_plan", "source_key", "title_evidence_signature",
]
