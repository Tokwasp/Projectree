# Migration 구조

Alembic에 노출되는 revision은 `versions/`에만 둔다.

```text
0001_initial
→ 0002_seed_categories
→ 0003_review_analysis
→ 0004_runtime_pipeline
```

배포되지 않았던 기존 0004~0010은 `0004_runtime_pipeline` 하나로
압축했다. `steps/`는 이 revision 내부의 기능별 DDL 구현이며 독립
revision이 아니다.

이미 예전 개발 revision을 로컬 DB에 적용했다면 `stamp`로 속이지
않는다. 보존할 데이터가 있으면 먼저 백업하고, 폐기 가능한 개발
DB라면 새 DB로 다시 `alembic upgrade head` 한다.
