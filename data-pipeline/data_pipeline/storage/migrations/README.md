# Migration 구조

Alembic에 노출되는 revision은 `versions/`에만 둔다.

```text
0001_initial
→ 0002_seed_categories
→ 0003_review_analysis
→ 0004_runtime_pipeline
→ 0005_manual_user_decisions
→ 0006_automatic_node_merge
```

배포되지 않았던 기존 0004~0010은 `0004_runtime_pipeline` 하나로
압축했다. `0005`는 분석 결과 없이도 사용자가 직접 MERGE할 수 있도록
병합 이력의 분석 provenance를 선택값으로 확장한다. `steps/`는 `0004`
revision 내부의 기능별 DDL 구현이며 독립
revision이 아니다.

`0006`은 자동 Graph 실행 경계(`generation_run`), immutable
`node_revision`/`evidence`, 논리 병합 계보와 Relation provenance를 additive하게
추가한다. 기존 Node는 `LEGACY` Revision으로 정직하게 backfill하며 원문으로
검증할 수 없는 Evidence를 새로 만들어내지 않는다.

이미 예전 개발 revision을 로컬 DB에 적용했다면 `stamp`로 속이지
않는다. 보존할 데이터가 있으면 먼저 백업하고, 폐기 가능한 개발
DB라면 새 DB로 다시 `alembic upgrade head` 한다.

`0006 → 0005` downgrade는 새 자동 Graph 테이블과 trigger를 제거할 수 있다.
그러나 과거 `0002` downgrade는 seed Category를 삭제하므로 Node 데이터가 있는
운영 DB의 `head → base`는 데이터 보존 절차가 아니다. 운영은 백업 후 forward
migration을 원칙으로 하고, 전체 왕복은 폐기 가능한 빈 DB에서만 수행한다.
