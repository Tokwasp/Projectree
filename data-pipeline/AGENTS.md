# AGENTS.md — Data Pipeline Repository Instructions

이 파일은 저장소 전체에 적용되는 Codex 작업 규칙이다.

## 1. 작업 시작 전 필수 읽기

항상 다음 순서로 읽는다.

1. `docs/contracts/automatic-node-merge.md`
2. `README.md`
3. 레거시 승인 흐름을 수정할 때만 `docs/CANDIDATE_NODE_CONFIRMATION_CONTRACT.md`
4. 현재 작업에서 별도 task 문서가 실제로 제공된 경우 해당 문서
5. 변경 대상 코드와 기존 테스트

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

- LLM 출력은 신뢰 경계 밖의 제안이며 서버 검증과 보수적 안전 게이트를 거친다.
- Candidate는 A 모델 원본·추적 데이터이며 사용자 승인 대기열이 아니다.
- 서버가 검증한 Evidence가 없는 자동 Revision은 공개하지 않는다.
- Decision을 먼저 canonical 확정한 뒤 Action/Issue 부모를 해석한다.
- 외부 호출 결과를 Graph Mutation Plan에 모으고 최종 그래프는 한 트랜잭션으로 반영한다.
- 정상 Decision은 `ACTIVE`, 유효한 구조 부모가 있는 Action/Issue도 `ACTIVE`다.
  필수 부모가 해결되지 않은 Action/Issue만 `UNATTACHED`로 보존한다.
- 자동 MERGE는 보정된 threshold·margin·동일성·충돌·target version 검사를 모두
  통과해야 하며, 실패하면 `CREATE_NEW`로 강등한다.
- 병합은 원본 Node/Revision/Evidence/Relation endpoint를 보존하는 논리 병합이다.
- Retrieval은 같은 프로젝트의 `ACTIVE`와 `UNATTACHED` Node를 검색하며 현재
  source와 `MERGED`·`EXCLUDED`·`ARCHIVED`·`DELETED` Node는 제외한다.
- 사용자 편집은 LLM을 호출하지 않고 새 Revision과 감사 정보를 만든다.
- 레거시 승인/재분석 API는 운영 제품 흐름에서 사용하지 않는다.

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

- 프론트엔드 UI
- Spring 사용자 인증 구현
- OpenVidu Meeting ID 정책 변경
- EC2/인프라 배포
- 자동 MERGE 임계값을 근거 없이 추측해 설정

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
