from __future__ import annotations

import pytest

from data_pipeline.normalization import (
    TermDictionary,
    TermEntry,
    apply_normalization_rules,
    build_normalization_rules,
    find_rule_matches,
    load_term_dictionary,
)


def _dictionary(terms: list[dict]) -> TermDictionary:
    return TermDictionary.model_validate(
        {
            "schema_version": "1.1",
            "dictionary_version": "2026-07-30.1",
            "terms": terms,
        }
    )


def test_build_rules_uses_only_enabled_terms_and_prefers_long_variants():
    dictionary = _dictionary(
        [
            {
                "id": "docker",
                "canonical": "Docker",
                "variants": ["도커"],
                "enabled": True,
            },
            {
                "id": "docker-compose",
                "canonical": "Docker Compose",
                "variants": ["도커 컴포즈"],
                "enabled": True,
            },
            {
                "id": "redis",
                "canonical": "Redis",
                "variants": ["레디스"],
                "enabled": False,
            },
        ]
    )

    rules = build_normalization_rules(dictionary)

    assert [rule.variant for rule in rules] == ["도커 컴포즈", "도커"]


def test_apply_rules_uses_longest_match_when_variants_overlap():
    rules = build_normalization_rules(
        _dictionary(
            [
                {
                    "id": "docker",
                    "canonical": "Docker",
                    "variants": ["도커"],
                },
                {
                    "id": "docker-compose",
                    "canonical": "Docker Compose",
                    "variants": ["도커 컴포즈"],
                },
            ]
        )
    )

    normalized = apply_normalization_rules(
        "도커 컴포즈로 실행하고 도커를 확인했다.",
        rules,
    )

    assert normalized == "Docker Compose로 실행하고 Docker를 확인했다."


def test_apply_rules_does_not_replace_inside_ascii_words():
    rules = build_normalization_rules(
        _dictionary(
            [
                {
                    "id": "s3",
                    "canonical": "S3",
                    "variants": ["s3"],
                }
            ]
        )
    )

    normalized = apply_normalization_rules(
        "s3와 s3-compatible은 바꾸고 s30과 my_s3는 유지한다.",
        rules,
    )

    assert normalized == "S3와 S3-compatible은 바꾸고 s30과 my_s3는 유지한다."


def test_apply_rules_keeps_korean_particles_around_a_variant():
    rules = build_normalization_rules(load_term_dictionary())

    normalized = apply_normalization_rules(
        "깃랩에서 젠킨스로 배포한다.",
        rules,
    )

    assert normalized == "GitLab에서 Jenkins로 배포한다."


def test_apply_rules_does_not_reprocess_replacement_output():
    rules = build_normalization_rules(
        _dictionary(
            [
                {
                    "id": "gitlab",
                    "canonical": "GitLab",
                    "variants": ["깃랩"],
                },
                {
                    "id": "other",
                    "canonical": "Other",
                    "variants": ["GitLab"],
                },
            ]
        )
    )

    normalized = apply_normalization_rules("깃랩을 사용한다.", rules)

    assert normalized == "GitLab을 사용한다."


def test_find_rule_matches_reports_original_positions_and_terms():
    rules = build_normalization_rules(load_term_dictionary())
    text = "깃랩과 레디스를 연결한다."

    matches = find_rule_matches(text, rules)

    assert [
        (match.rule.term_id, match.original, match.start, match.end)
        for match in matches
    ] == [
        ("gitlab", "깃랩", 0, 2),
        ("redis", "레디스", 4, 7),
    ]


def test_apply_rules_returns_unchanged_text_when_nothing_matches():
    rules = build_normalization_rules(load_term_dictionary())
    text = "회의 내용을 그대로 유지한다."

    assert apply_normalization_rules(text, rules) == text


def test_every_default_dictionary_variant_normalizes_to_its_canonical():
    dictionary = load_term_dictionary()
    rules = build_normalization_rules(dictionary)

    for term in dictionary.terms:
        for variant in term.variants:
            assert apply_normalization_rules(variant, rules) == term.canonical, (
                f"{variant!r}가 {term.canonical!r}로 변환되지 않았습니다."
            )


def test_ambiguous_fragments_from_evaluation_remain_unchanged():
    rules = build_normalization_rules(load_term_dictionary())
    text = "3개와 q 하나, 에디슨 전구와 독후 활동"

    assert apply_normalization_rules(text, rules) == text


def test_rule_builder_rejects_empty_variant_even_if_contract_is_bypassed():
    term = TermEntry.model_construct(
        id="broken",
        canonical="Broken",
        variants=[""],
        match_mode="word",
        case_sensitive=True,
        enabled=True,
    )
    dictionary = TermDictionary.model_construct(
        schema_version="1.1",
        dictionary_version="2026-07-30.3",
        terms=[term],
    )

    with pytest.raises(ValueError, match="variant must not be empty"):
        build_normalization_rules(dictionary)


def test_rule_builder_rejects_duplicate_variant_if_contract_is_bypassed():
    first = TermEntry.model_construct(
        id="gitlab",
        canonical="GitLab",
        variants=["깃랩"],
        match_mode="word",
        case_sensitive=True,
        enabled=True,
    )
    second = TermEntry.model_construct(
        id="github",
        canonical="GitHub",
        variants=["깃랩"],
        match_mode="word",
        case_sensitive=True,
        enabled=True,
    )
    dictionary = TermDictionary.model_construct(
        schema_version="1.1",
        dictionary_version="2026-07-30.3",
        terms=[first, second],
    )

    with pytest.raises(ValueError, match="duplicate normalization variant"):
        build_normalization_rules(dictionary)


def test_word_mode_blocks_embedded_hangul_but_allows_korean_particles():
    rules = build_normalization_rules(load_term_dictionary())
    text = (
        "네잎클로버는 식물이고 클로버에서만 처리한다. "
        "우리깃랩과 깃랩에서는"
    )

    normalized = apply_normalization_rules(text, rules)

    assert normalized == (
        "네잎클로버는 식물이고 CLOVA에서만 처리한다. "
        "우리깃랩과 GitLab에서는"
    )


def test_case_insensitive_rule_normalizes_case_without_recording_no_op():
    rules = build_normalization_rules(load_term_dictionary())
    text = "gitlab GITLAB GitLab"

    matches = find_rule_matches(text, rules)
    normalized = apply_normalization_rules(text, rules)

    assert normalized == "GitLab GitLab GitLab"
    assert [match.original for match in matches] == ["gitlab", "GITLAB"]


def test_rule_matches_flexible_whitespace_without_changing_source_offsets():
    rules = build_normalization_rules(load_term_dictionary())
    text = "깃   랩에서 배포한다."

    matches = find_rule_matches(text, rules)
    normalized = apply_normalization_rules(text, rules)

    assert normalized == "GitLab에서 배포한다."
    assert len(matches) == 1
    assert matches[0].original == "깃   랩"
    assert text[matches[0].start : matches[0].end] == "깃   랩"


def test_rule_whitespace_does_not_cross_line_breaks():
    dictionary = _dictionary(
        [
            {
                "id": "spring-boot",
                "canonical": "Spring Boot",
                "variants": ["스프링 부트"],
            }
        ]
    )
    rules = build_normalization_rules(dictionary)

    assert apply_normalization_rules("스프링\t부트", rules) == "Spring Boot"
    assert apply_normalization_rules("스프링\n부트", rules) == "스프링\n부트"


def test_substring_mode_is_available_only_when_dictionary_requests_it():
    dictionary = _dictionary(
        [
            {
                "id": "lab",
                "canonical": "LAB",
                "variants": ["랩"],
                "match_mode": "substring",
            }
        ]
    )
    rules = build_normalization_rules(dictionary)

    assert apply_normalization_rules("깃랩", rules) == "깃LAB"
