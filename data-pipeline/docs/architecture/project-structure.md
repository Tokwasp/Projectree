# 프로젝트 구조와 의존 방향

## Runtime

```text
api / worker
→ pipeline
→ retrieval / storage / provider ports
→ contracts / config
```

- `api/`: Spring 등 내부 호출자를 위한 HTTP 경계다.
- `worker/`: SQS/S3 음성 입력과 자동 Graph 실행 진입점이다.
- `pipeline/`: Decision-first plan, Revision, Relation, Merge 등 제품 규칙이다.
- `retrieval/`: canonical Embedding 계약, provider adapter, pgvector 검색이다.
- `storage/`: SQLAlchemy ORM과 Alembic 정본이다.

## Operations

```text
scripts/operations
→ data_pipeline/operations
→ retrieval / storage
```

`operations/`는 backfill처럼 제품 데이터를 제한적으로 유지보수하는
orchestration이다. 기본 dry-run과 project scope를 유지하며 core 검색 모듈에
CLI·보고서 책임을 넣지 않는다. 기존 CLI/import는 얇은 wrapper로 호환한다.

## Evaluation

```text
scripts/evaluation
→ data_pipeline/evaluation
→ retrieval / storage의 read-only query
```

평가 코드는 Graph apply, Node/Relation/Revision mutation, Outbox 생성을 호출하지
않는다. 실행 전후 제품 테이블의 row count와 PK checksum을 비교하고 결과는
`outputs/` 파일에만 쓴다. 라벨 없는 pilot을 의미 정확도 정답으로 취급하지
않으며 운영 threshold를 자동 변경하지 않는다.

## 테스트와 문서

- `tests/operations/`: 운영 도구의 안전·멱등성·동시성 검증
- `tests/evaluation/`: 평가 계약, 추출, read-only, metrics, simulator 검증
- `tests/`: core runtime 및 통합 회귀
- `docs/contracts/`: 현재 제품 계약
- `docs/operations/`: 운영 절차
- `docs/evaluation/`: 라벨링과 평가 해석
- `outputs/`: 커밋하지 않는 실행 결과

Migration, fixture, 사용자 보고서는 구조 정리를 이유로 삭제하지 않는다.
