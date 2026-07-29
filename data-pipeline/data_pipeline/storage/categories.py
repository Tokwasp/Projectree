"""카테고리 reference 테이블 재시딩 (설정 → DB).

값 교체 절차 = ① config/categories.json 수정 ② 재시딩 마이그레이션 1개 실행.
FK 안전을 위해 목록에서 빠진 값은 삭제하지 않고 is_active=False 로 비활성화한다
(기존 노드의 category FK 를 깨지 않기 위함). 활성 집합의 강제는 validation 레이어(CategorySet).
"""

from __future__ import annotations

from sqlalchemy import Connection, select

from .models import Category


def reseed_categories(conn: Connection, values: list[str], schema_version: str) -> dict[str, int]:
    """새 값 목록으로 category 테이블을 재시딩. 반환: {inserted, reactivated, deactivated}."""
    table = Category.__table__
    existing = {row.value: row for row in conn.execute(select(table)).mappings()}
    new_set = list(dict.fromkeys(values))  # 순서 보존 dedup

    inserted = reactivated = 0
    for position, value in enumerate(new_set):
        if value in existing:
            conn.execute(
                table.update()
                .where(table.c.value == value)
                .values(position=position, is_active=True, schema_version=schema_version)
            )
            if not existing[value]["is_active"]:
                reactivated += 1
        else:
            conn.execute(
                table.insert().values(
                    value=value, position=position, is_active=True, schema_version=schema_version
                )
            )
            inserted += 1

    deactivated = 0
    for value, row in existing.items():
        if value not in new_set and row["is_active"]:
            conn.execute(table.update().where(table.c.value == value).values(is_active=False))
            deactivated += 1

    return {"inserted": inserted, "reactivated": reactivated, "deactivated": deactivated}


def active_category_values(conn: Connection) -> list[str]:
    table = Category.__table__
    rows = conn.execute(
        select(table.c.value).where(table.c.is_active.is_(True)).order_by(table.c.position)
    ).scalars()
    return list(rows)
