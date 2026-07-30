from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from data_pipeline.normalization import (
    TermDictionary,
    calculate_dictionary_sha256,
    load_term_dictionary,
)


def _term(
    *,
    term_id: str = "redis",
    canonical: str = "Redis",
    variants: list[str] | None = None,
    enabled: bool = True,
) -> dict:
    return {
        "id": term_id,
        "canonical": canonical,
        "variants": variants or ["레디스"],
        "enabled": enabled,
    }


def _dictionary(terms: list[dict]) -> dict:
    return {
        "schema_version": "1.1",
        "dictionary_version": "2026-07-30.1",
        "terms": terms,
    }


def test_default_dictionary_loads_and_is_fully_enabled():
    dictionary = load_term_dictionary()

    assert dictionary.schema_version == "1.1"
    assert dictionary.dictionary_version == "2026-07-30.3"
    assert len(dictionary.terms) == 27
    assert sum(len(term.variants) for term in dictionary.terms) == 55
    assert all(term.enabled for term in dictionary.terms)


def test_loader_validates_custom_json_file(tmp_path):
    path = tmp_path / "terms.json"
    path.write_text(
        json.dumps(_dictionary([_term()]), ensure_ascii=False),
        encoding="utf-8",
    )

    dictionary = load_term_dictionary(path)

    assert dictionary.terms[0].canonical == "Redis"


def test_contract_rejects_unknown_fields():
    payload = _dictionary([_term()])
    payload["unexpected"] = "value"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        TermDictionary.model_validate(payload)


def test_contract_rejects_duplicate_ids():
    payload = _dictionary(
        [
            _term(),
            _term(canonical="Redis Cache", variants=["레디스 캐시"]),
        ]
    )

    with pytest.raises(ValidationError, match="중복된 term id"):
        TermDictionary.model_validate(payload)


def test_contract_rejects_duplicate_variants_across_terms():
    payload = _dictionary(
        [
            _term(),
            _term(
                term_id="redis-cache",
                canonical="Redis Cache",
                variants=["레디스"],
            ),
        ]
    )

    with pytest.raises(ValidationError, match="중복된 variant"):
        TermDictionary.model_validate(payload)


def test_contract_rejects_empty_and_exact_canonical_variants():
    with pytest.raises(ValidationError, match="빈 문자열"):
        TermDictionary.model_validate(
            _dictionary([_term(variants=[" "])])
        )

    with pytest.raises(ValidationError, match="canonical과 완전히 같은"):
        TermDictionary.model_validate(
            _dictionary([_term(variants=["Redis"])])
        )


def test_contract_allows_case_only_normalization_but_requires_boolean_enabled():
    dictionary = TermDictionary.model_validate(
        _dictionary(
            [
                _term(
                    term_id="s3",
                    canonical="S3",
                    variants=["s3"],
                )
            ]
        )
    )
    assert dictionary.terms[0].canonical == "S3"

    payload = _dictionary([_term()])
    payload["terms"][0]["enabled"] = "true"
    with pytest.raises(ValidationError, match="bool_type"):
        TermDictionary.model_validate(payload)


def test_contract_rejects_unknown_match_mode_and_non_boolean_case_policy():
    payload = _dictionary([_term()])
    payload["terms"][0]["match_mode"] = "unknown"

    with pytest.raises(ValidationError, match="literal_error"):
        TermDictionary.model_validate(payload)

    payload = _dictionary([_term()])
    payload["terms"][0]["case_sensitive"] = "false"

    with pytest.raises(ValidationError, match="bool_type"):
        TermDictionary.model_validate(payload)


def test_contract_requires_nfkc_canonical_and_variants():
    with pytest.raises(ValidationError, match="canonical은 NFKC"):
        TermDictionary.model_validate(
            _dictionary(
                [
                    _term(
                        canonical="Ｒedis",
                        variants=["레디스"],
                    )
                ]
            )
        )

    with pytest.raises(ValidationError, match="variant는 NFKC"):
        TermDictionary.model_validate(
            _dictionary([_term(variants=["Ｒedis"])])
        )


def test_dictionary_sha256_tracks_content_not_only_version():
    first = TermDictionary.model_validate(
        _dictionary([_term(variants=["레디스"])])
    )
    second = TermDictionary.model_validate(
        _dictionary([_term(variants=["랜디스"])])
    )

    first_hash = calculate_dictionary_sha256(first)
    second_hash = calculate_dictionary_sha256(second)

    assert len(first_hash) == 64
    assert first_hash != second_hash
