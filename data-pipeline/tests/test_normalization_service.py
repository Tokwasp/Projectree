from __future__ import annotations

import pytest

from data_pipeline.normalization import (
    SttNormalizationService,
    get_default_normalization_service,
    initialize_default_normalization_service,
)
from data_pipeline.normalization.service import _normalize_nfkc_with_offsets


def test_service_normalizes_terms_and_returns_original_offsets():
    service = SttNormalizationService.from_dictionary_file()
    text = "깃   랩에서 GITLAB을 확인한다."

    result = service.normalize(text)

    assert result.original_text == text
    assert result.normalized_text == "GitLab에서 GitLab을 확인한다."
    assert result.dictionary_version == "2026-07-30.3"
    assert result.unicode_normalized is False
    assert [
        (
            change.term_id,
            change.original,
            change.matched_text,
            change.original_start,
            change.original_end,
            change.normalized_start,
            change.normalized_end,
        )
        for change in result.changes
    ] == [
        ("gitlab", "깃   랩", "깃   랩", 0, 5, 0, 6),
        ("gitlab", "GITLAB", "GITLAB", 8, 14, 9, 15),
    ]
    assert result.schema_version == "1.1"
    assert len(result.dictionary_sha256) == 64


def test_service_applies_nfkc_to_fullwidth_text():
    service = SttNormalizationService.from_dictionary_file()

    result = service.normalize("ＧｉｔＬａｂ")

    assert result.normalized_text == "GitLab"
    assert result.unicode_normalized is True
    assert result.changes == []


def test_service_maps_nfkc_term_match_back_to_original_positions():
    service = SttNormalizationService.from_dictionary_file()
    text = "ﬁ와 ＧＩＴＬＡＢ에서"

    result = service.normalize(text)

    assert result.normalized_text == "fi와 GitLab에서"
    assert result.unicode_normalized is True
    assert len(result.changes) == 1

    change = result.changes[0]
    assert change.term_id == "gitlab"
    assert change.original == "ＧＩＴＬＡＢ"
    assert change.matched_text == "GITLAB"
    assert (change.original_start, change.original_end) == (3, 9)
    assert (change.normalized_start, change.normalized_end) == (4, 10)
    assert (
        text[change.original_start : change.original_end]
        == change.original
    )
    assert (
        result.normalized_text[
            change.normalized_start : change.normalized_end
        ]
        == change.canonical
    )


def test_service_enforces_input_length_limit():
    service = SttNormalizationService.from_dictionary_file(
        max_input_text_length=5
    )

    with pytest.raises(ValueError, match="max_input_text_length"):
        service.normalize("123456")


def test_unchanged_nfkc_input_does_not_allocate_offset_tuples():
    normalized_input = _normalize_nfkc_with_offsets(
        "일반적인 STT 문장",
        max_normalized_text_length=100,
    )

    assert normalized_input.original_spans is None
    assert normalized_input.original_span(2, 5) == (2, 5)


def test_service_enforces_normalized_length_after_nfkc_expansion():
    service = SttNormalizationService.from_dictionary_file(
        max_input_text_length=10,
        max_normalized_text_length=3,
    )

    with pytest.raises(ValueError, match="max_normalized_text_length"):
        service.normalize("ﬁﬁ")


def test_default_service_is_cached_with_precompiled_rules():
    first = get_default_normalization_service()
    second = get_default_normalization_service()
    initialized = initialize_default_normalization_service()

    assert first is second
    assert initialized is first
    assert first.rule_count == 55
    assert len(first.dictionary_sha256) == 64
