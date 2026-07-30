# AGENTS.md — Data Pipeline Repository Instructions

이 파일은 저장소 전체에 적용되는 Codex 작업 규칙이다.

## 1. 작업 시작 전 필수 읽기

항상 다음 순서로 읽는다.

1. `docs/CANDIDATE_NODE_CONFIRMATION_CONTRACT.md`
2. `README.md`
3. 현재 작업에서 별도 task 문서가 실제로 제공된 경우 해당 문서
4. 변경 대상 코드와 기존 테스트

문서와 코드가 충돌하면 임의로 추측하지 말고, 현재 task의 완료 조건을 만족하는 최소 변경을 우선한다.

## 2. 절대 변경 금지

- `data_pipeline/prompts/assets/extraction_poc_v3_lts.md`
- `data_pipeline/prompts/assets/judgment_poc_v4_lts.md`
- 위 두 PromptAsset의 SHA-256 및 registry lock
- 기본 pipeline profile `poc-lts`
- `poc-lts`의 extraction/judgment pair
- PoC LLM judgment enum에 `UNATTACHED` 추가
- 기존 테스트 삭제 또는 assertion 완화
- `.env`, API key, raw secret 로그 출력

프롬프트는 2026-07-29 기준 동결됐다. 현재 이후 작업은 프롬프트 최적화가 아니라 저장·검토·승인·검색 파이프라인 구현이다.

## 3. 현재 제품 원칙

- LLM 출력은 정답이 아니라 제안이다.
- 모든 extraction item은 먼저 `PROPOSED` 후보로 저장한다.
- judgment 결과는 `suggestedDisposition`과 `suggestedParent`일 뿐이다.
- `MINUTES_ONLY`로 추천된 항목도 삭제하거나 숨기지 않는다.
- 1차 검토가 끝난 Candidate만 `UNATTACHED Node`로 만들고, 사용자가 최종
  승인한 결과만 `ACTIVE` 그래프에 반영한다.
- 생성 파이프라인은 Candidate 1차 검토 완료 전에 `Node`와 정식 `NodeEvidence`를 만들면 안 된다.
- 1차 검토 완료 후에는 `UNATTACHED` Node와 Evidence만 만들며, 최종 승인 전에는
  `ACTIVE` 전환이나 `Relation` 생성을 하면 안 된다.
- Retrieval은 같은 프로젝트의 `ACTIVE`와 `UNATTACHED` Node를 검색하며,
  현재 검색 Node 자신과 `MERGED`·`EXCLUDED`·`ARCHIVED` Node는 제외한다.
- Retrieval과 B 모델은 추천만 생성하고 Node·Relation을 직접 변경하지 않는다.

## 4. 코드베이스 규칙

- Python, SQLAlchemy 2.0, Pydantic 계약을 유지한다.
- 내부 PK는 UUID를 유지한다.
- DB 변경은 Alembic의 additive migration으로 수행한다.
- 기존 테이블/컬럼의 destructive rename/drop을 하지 않는다.
- PostgreSQL 기능과 SQLite 테스트 호환성을 모두 고려한다.
- 트랜잭션 실패 시 부분 성공을 남기지 않는다.
- 동시 수정 경계에는 기존 `version` 기반 optimistic locking 원칙을 유지한다.
- 테스트는 네트워크와 실제 LLM 호출 없이 실행돼야 한다.
- 실험 결과는 `outputs/`에만 기록하며 Git에 커밋하지 않는다.

## 5. 범위 통제

현재 task 문서에 없는 다음 작업을 한 PR에 섞지 않는다.

- pgvector 설치 및 임베딩 worker
- Top-K retrieval
- RAG prompt 입력 연결
- Clova STT 연동
- merge/same/follows/reverses/resolved_by 구현 확대
- HTTP 프레임워크 도입
- 프론트엔드 UI
- 프롬프트 재작성

## 6. 검증

변경 후 최소한 다음을 실행한다.

```bash
pytest -q
```

DB migration이 바뀌면 Alembic head까지 실제 upgrade되는지 검증한다. 테스트를 실행하지 못했다면 이유와 미검증 범위를 명시한다.

## 7. 완료 보고 형식

작업 완료 시 다음을 보고한다.

1. 변경한 파일
2. DB migration 요약
3. public behavior 변경
4. 추가한 테스트
5. 실행한 명령과 결과
6. 남은 위험 또는 다음 작업

테스트 통과를 위해 기능을 우회하거나 테스트를 약화하지 않는다.
