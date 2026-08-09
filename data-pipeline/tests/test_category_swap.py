"""완료 기준 4 — category 값 교체가 설정 + 마이그레이션 1개로 가능함을 증명.

절차: config 수정(여기서는 임시 파일) + 재시딩 1개(reseed_categories) → 새 값 사용 가능,
제거된 값은 validation(CategorySet)에서 거부. FK 안전을 위해 제거 값은 비활성화(삭제 아님).
"""

from __future__ import annotations

import json

from data_pipeline.contracts import CategorySet
from data_pipeline.pipeline import seed_node
from data_pipeline.storage import active_category_values, reseed_categories, session_scope

NEW_VALUES = ["PLANNING", "DESIGN", "FRONTEND", "BACKEND", "AI", "INFRA", "SECURITY"]  # ETC→SECURITY


def test_category_swap_via_config_and_one_migration(session_factory, tmp_path):
    engine = None
    with session_factory() as s:
        engine = s.get_bind()

    # (마이그레이션 1개에 해당하는) 재시딩 실행.
    with engine.begin() as conn:
        stats = reseed_categories(conn, NEW_VALUES, "cat-v2")
        assert stats["inserted"] == 1 and stats["deactivated"] == 1

    with engine.connect() as conn:
        assert active_category_values(conn) == NEW_VALUES

    # 새 카테고리로 노드 생성 가능 (FK 만족).
    with session_scope(session_factory) as s:
        node = seed_node(s, project_id="proj-01", source_meeting_id="M9", source_item_id="m1",
                         node_type="DECISION", category="SECURITY", title="보안 결정")
        assert node.category == "SECURITY"

    # config 파일 교체분을 읽은 CategorySet 은 새 값 허용, 제거 값 거부.
    cfg = tmp_path / "categories.json"
    cfg.write_text(json.dumps({"schemaVersion": "cat-v2", "values": NEW_VALUES}), encoding="utf-8")
    cs = CategorySet.load(cfg)
    assert cs.is_valid("SECURITY")
    assert not cs.is_valid("ETC")
    assert cs.schema_version == "cat-v2"
