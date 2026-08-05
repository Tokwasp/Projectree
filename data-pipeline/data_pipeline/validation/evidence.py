"""규칙 4 — evidence 검증.

segmentId 실존 + quote 가 세그먼트 원문의 부분 문자열 + 최소 10자 + 서버 오프셋 역산.
클라이언트(LLM)가 준 오프셋은 신뢰하지 않고 서버가 세그먼트 내 char 오프셋을 역산한다.
정규화 매칭은 오프셋을 정확히 되돌릴 수 없으므로 char 오프셋은 None 으로 둔다(부분 문자열은 인정).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import normalize_quote

MIN_QUOTE_CHARS = 10  # "네" 같은 무의미 quote 우회 차단


@dataclass(frozen=True)
class SegmentInfo:
    text: str
    start_ms: int | None = None


@dataclass
class ResolvedEvidence:
    segment_id: str
    start_ms: int | None
    char_start: int | None
    char_end: int | None
    match: str  # EXACT / NORMALIZED / INVALID


@dataclass
class EvidenceResolution:
    item_id: str
    valid: bool
    problems: list[str] = field(default_factory=list)
    resolved: list[ResolvedEvidence] = field(default_factory=list)
    earliest_start_ms: int | None = None
    earliest_segment_id: str | None = None


def _match_offsets(quote: str, text: str) -> tuple[str, int | None, int | None]:
    idx = text.find(quote)
    if idx >= 0:
        return "EXACT", idx, idx + len(quote)
    if normalize_quote(quote) and normalize_quote(quote) in normalize_quote(text):
        return "NORMALIZED", None, None
    return "INVALID", None, None


def resolve_item_evidence(item: dict, segments: dict[str, SegmentInfo]) -> EvidenceResolution:
    item_id = str(item.get("id"))
    evidence = item.get("evidence") or []
    problems: list[str] = []
    resolved: list[ResolvedEvidence] = []
    if not evidence:
        return EvidenceResolution(item_id, False, ["no evidence"])

    for ev in evidence:
        segment_id = ev.get("segmentId")
        quote = (ev.get("quote") or "").strip()
        if segment_id not in segments:
            problems.append(f"missing segmentId {segment_id!r}")
            continue
        if len(quote) < MIN_QUOTE_CHARS:
            problems.append(f"quote too short (<{MIN_QUOTE_CHARS}) in {segment_id}")
            continue
        info = segments[segment_id]
        match, cstart, cend = _match_offsets(quote, info.text)
        if match == "INVALID":
            problems.append(f"quote not in {segment_id}")
            continue
        resolved.append(ResolvedEvidence(segment_id, info.start_ms, cstart, cend, match))

    valid = not problems and bool(resolved)
    earliest_ms = None
    earliest_seg = None
    if resolved:
        # 정렬 키(규칙 6)용: 가장 이른 evidence.
        keyed = sorted(
            resolved,
            key=lambda r: (r.start_ms if r.start_ms is not None else 2_147_483_647, r.segment_id),
        )
        earliest_ms = keyed[0].start_ms
        earliest_seg = keyed[0].segment_id
    return EvidenceResolution(item_id, valid, problems, resolved, earliest_ms, earliest_seg)
