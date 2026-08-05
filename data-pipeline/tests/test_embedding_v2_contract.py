"""Embedding v2 contract: Category is excluded from the Retrieval meaning.

v1 serialized [node_type, category, title, content, evidence].
v2 serializes  [node_type, title, content, evidence].

Category stays on Node/NodeRevision metadata, screens, search scoping, stats,
B-model input and the MERGE gate — it just no longer changes the vector.
"""

from __future__ import annotations

import json

import pytest

from data_pipeline.config import load_settings
from data_pipeline.retrieval.embedding import (
    build_embedding_text_from_parts,
    embedding_text_hash,
)

EVIDENCE = [("segment-1", "근거 문장"), ("segment-2", "두 번째 근거")]


def _text(**overrides) -> str:
    kwargs = {
        "node_type": "ACTION",
        "title": "제목",
        "content": "내용",
        "evidence_pairs": list(EVIDENCE),
    }
    kwargs.update(overrides)
    return build_embedding_text_from_parts(**kwargs)


def _hash(**overrides) -> str:
    return embedding_text_hash(_text(**overrides))


# ------------------------------------------------------- category excluded ---


def test_v2_serialization_has_exactly_four_parts_without_category() -> None:
    parsed = json.loads(_text())
    assert parsed == [
        "ACTION",
        "제목",
        "내용",
        [["segment-1", "근거 문장"], ["segment-2", "두 번째 근거"]],
    ]


def test_different_categories_produce_the_same_v2_hash() -> None:
    """The whole point of v2: category must not move the vector."""

    backend = _hash(category="BACKEND")
    infra = _hash(category="INFRA")
    none_given = _hash()
    assert backend == infra == none_given


def test_category_string_never_appears_in_the_serialized_text() -> None:
    text = _text(category="INFRA")
    assert "INFRA" not in text


# ------------------------------------------------- meaning fields still bite ---


@pytest.mark.parametrize(
    "override",
    [
        {"title": "다른 제목"},
        {"content": "다른 내용"},
        {"node_type": "DECISION"},
        {"evidence_pairs": [("segment-1", "바뀐 근거")]},
        {"evidence_pairs": [*EVIDENCE, ("segment-3", "추가 근거")]},
    ],
)
def test_meaning_changes_change_the_hash(override: dict) -> None:
    assert _hash(**override) != _hash()


def test_evidence_order_does_not_change_the_hash() -> None:
    assert _hash(evidence_pairs=list(reversed(EVIDENCE))) == _hash()


def test_evidence_uses_start_ms_only_for_ordering() -> None:
    text = _text(
        evidence_pairs=[
            (900, "segment-1", "나중 근거"),
            (100, "segment-2", "먼저 근거"),
        ]
    )
    parsed = json.loads(text)
    assert parsed[-1] == [["segment-2", "먼저 근거"], ["segment-1", "나중 근거"]]
    assert "900" not in text
    assert "100" not in text


def test_missing_segment_id_is_normalized_to_empty_string() -> None:
    assert _hash(evidence_pairs=[(None, "근거")]) == _hash(
        evidence_pairs=[("", "근거")]
    )


def test_json_options_follow_the_existing_contract() -> None:
    text = _text(title="한글", content="공백 없음")
    assert "\\u" not in text          # ensure_ascii=False
    assert ", " not in text           # separators=(",", ":")
    assert '": "' not in text


# ------------------------------------------------------------ version bump ---


def test_configured_embedding_version_is_the_v2_contract() -> None:
    load_settings.cache_clear()
    assert (
        load_settings().retrieval.embedding_version
        == "node-embedding-v2-no-category"
    )


def test_version_string_fits_the_embedding_version_column() -> None:
    """node_embedding.embedding_version is varchar(64) (0007) and part of the PK.

    PostgreSQL enforces the width, SQLite does not — a longer contract name
    passes the SQLite suite and then fails every PostgreSQL insert.
    """

    from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
    from data_pipeline.storage.models import NodeEmbedding

    column = NodeEmbedding.__table__.c.embedding_version
    assert len(EMBEDDING_CONTRACT_VERSION) <= column.type.length
