"""Contracts for the versioned STT term dictionary."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

MAX_DICTIONARY_TERMS = 1_000
MAX_DICTIONARY_VARIANTS = 2_000
MAX_TERM_VARIANTS = 100
MAX_TERM_TEXT_LENGTH = 128

MatchMode = Literal["word", "substring"]


def _text_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class TermEntry(BaseModel):
    """변환 규칙"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: str = Field(
        min_length=1,
        max_length=MAX_TERM_TEXT_LENGTH,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )

    canonical: str = Field(
        min_length=1,
        max_length=MAX_TERM_TEXT_LENGTH,
    )
    variants: list[str] = Field(
        min_length=1,
        max_length=MAX_TERM_VARIANTS,
    )
    match_mode: MatchMode = "word"
    case_sensitive: StrictBool = True
    enabled: StrictBool = True

    @field_validator("canonical")
    @classmethod
    def canonical_must_be_nfkc(cls, canonical: str) -> str:
        if unicodedata.normalize("NFKC", canonical) != canonical:
            raise ValueError("canonical은 NFKC 형식이어야 합니다.")
        return canonical

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, variants: list[str]) -> list[str]:
        cleaned = [variant.strip() for variant in variants]

        if any(not variant for variant in cleaned):
            raise ValueError("variant는 빈 문자열일 수 없습니다.")

        if any(len(variant) > MAX_TERM_TEXT_LENGTH for variant in cleaned):
            raise ValueError(
                f"variant는 {MAX_TERM_TEXT_LENGTH}자를 넘을 수 없습니다."
            )

        if any(
            unicodedata.normalize("NFKC", variant) != variant
            for variant in cleaned
        ):
            raise ValueError("variant는 NFKC 형식이어야 합니다.")

        keys = [_text_key(variant) for variant in cleaned]

        if len(keys) != len(set(keys)):
            raise ValueError("한 용어 안에 중복된 variant가 있습니다.")

        return cleaned

    @model_validator(mode="after")
    def canonical_must_not_equal_variant(self) -> "TermEntry":
        # 대소문자만 바꾸는 변환(s3 → S3)은 허용한다.
        canonical = unicodedata.normalize(
            "NFKC", self.canonical
        ).strip()

        variants = {
            unicodedata.normalize("NFKC", variant).strip()
            for variant in self.variants
        }

        if canonical in variants:
            raise ValueError(
                "canonical과 완전히 같은 variant는 등록할 수 없습니다."
            )

        return self


class TermDictionary(BaseModel):
    """stt_terms.json 전체 계약."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"]
    dictionary_version: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}\.\d+$"
    )
    terms: list[TermEntry] = Field(
        min_length=1,
        max_length=MAX_DICTIONARY_TERMS,
    )

    @model_validator(mode="after")
    def validate_dictionary(self) -> "TermDictionary":
        variant_count = sum(len(term.variants) for term in self.terms)
        if variant_count > MAX_DICTIONARY_VARIANTS:
            raise ValueError(
                "전체 variant는 "
                f"{MAX_DICTIONARY_VARIANTS}개를 넘을 수 없습니다."
            )

        ids: set[str] = set()
        canonicals: set[str] = set()
        variants: set[str] = set()

        for term in self.terms:
            if term.id in ids:
                raise ValueError(
                    f"중복된 term id가 있습니다: {term.id}"
                )
            ids.add(term.id)

            canonical_key = _text_key(term.canonical)
            if canonical_key in canonicals:
                raise ValueError(
                    f"중복된 canonical이 있습니다: {term.canonical}"
                )
            canonicals.add(canonical_key)

            for variant in term.variants:
                variant_key = _text_key(variant)

                if variant_key in variants:
                    raise ValueError(
                        f"서로 다른 용어에서 중복된 variant가 있습니다: "
                        f"{variant}"
                    )

                variants.add(variant_key)

        return self


class NormalizationChange(BaseModel):
    """A term replacement with original and final-text offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    term_id: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    original: str = Field(min_length=1)
    matched_text: str = Field(min_length=1)
    canonical: str = Field(min_length=1)
    original_start: int = Field(ge=0)
    original_end: int = Field(gt=0)
    normalized_start: int = Field(ge=0)
    normalized_end: int = Field(gt=0)

    @model_validator(mode="after")
    def ends_must_follow_starts(self) -> "NormalizationChange":
        if self.original_end <= self.original_start:
            raise ValueError(
                "original_end는 original_start보다 커야 합니다."
            )
        if self.normalized_end <= self.normalized_start:
            raise ValueError(
                "normalized_end는 normalized_start보다 커야 합니다."
            )
        return self


class NormalizationResult(BaseModel):
    """Complete STT normalization result with original-text offsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.1"] = "1.1"
    dictionary_version: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}\.\d+$"
    )
    dictionary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    unicode_form: Literal["NFKC"] = "NFKC"
    unicode_normalized: StrictBool
    original_text: str
    normalized_text: str
    changes: list[NormalizationChange]
