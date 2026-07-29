"""검색기 (③ IF-3). **M1 에서는 구현 없음 — 설정 스텁만.**

실제 하이브리드 검색(pg_bigm 텍스트 + pgvector + 용어/카테고리 부스트, RRF)은 후속
마일스톤에서 구현한다. 튜너블 값(Top-K 등)은 코드 상수가 아니라
`data_pipeline.config.RetrievalSettings`(환경변수 주입)로 관리한다.
"""

from __future__ import annotations

from data_pipeline.config import RetrievalSettings, load_settings


def retrieval_settings() -> RetrievalSettings:
    """현재 검색 설정 스텁을 반환한다. (검색 로직은 미구현.)"""
    return load_settings().retrieval


__all__ = ["RetrievalSettings", "retrieval_settings"]
