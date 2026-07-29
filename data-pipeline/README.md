# data-pipeline

노드 생성 파이프라인. **토폴로지 A**: 그래프 **정본(source of truth)은 이 파이썬 프로젝트가
소유하는 PostgreSQL** 이다. 스프링(`../Backend/`)은 이 그래프 DB 에 **직접 접근하지 않고**,
파이프라인이 발행하는 범용 `outbox_event` 및 API/메시지로만 통신한다(연동 자체는 M4).

> ⚠️ **그래프 정본 = 이 PG. 스프링 직접 접근 금지.** 스키마 변경·쓰기는 이 프로젝트의 alembic
> 마이그레이션·apply 경로를 통해서만 이뤄진다.

## M1 범위
contracts + storage(+alembic) + validation + **가짜 JSON E2E**. 이번 마일스톤에 **LLM 호출 0건**,
검색기 구현 0건(설정 스텁만). M2(프롬프트 재작성 + ①② 연결)는 별도.

## 빠른 시작 (정본 PostgreSQL)
```bash
cd data-pipeline
cp .env.example .env                     # 필요시 값 수정 (.env 는 커밋 금지)
docker compose up -d                     # PG16 + pgvector
pip install -e ".[dev]"                  # 또는 python -m venv .venv 후 설치
export DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline
alembic upgrade head                     # 정본 스키마 구축 (D1'~D1''')
pytest                                    # 전체 테스트 (E2E 포함) green
```

### Docker 없이 (로컬/CI 스모크)
정본은 PostgreSQL 이지만, 같은 ORM·같은 마이그레이션이 SQLite 에서도 뜨도록 방언 인지 타입으로
작성돼 있다. 테스트 하네스(`tests/conftest.py`)는 기본적으로 **임시 SQLite 파일에 alembic upgrade
head 를 돌린 뒤** 테스트한다 — Docker/PG 없이도 `pytest` 만으로 완료 기준을 검증할 수 있다.
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                                    # SQLite 로 30개 테스트 green
```
실제 PG 로 테스트하려면 `DATABASE_URL_TEST=postgresql+psycopg://... pytest`.

> **이 개발 환경(WSL) 한계**: 현재 셸에서 Docker 데몬이 동작하지 않아(`docker` I/O 에러) `docker
> compose up` 실물 검증은 못 했다. 대신 alembic 마이그레이션·전체 테스트를 SQLite 로 green 확인했고,
> 마이그레이션 DDL·docker-compose 는 PG 기준으로 작성돼 있다. Docker 가능한 환경/CI 에서
> `pgvector/pgvector:pg16` 로 동일하게 동작한다.

## 디렉터리
```
data-pipeline/
├── data_pipeline/
│   ├── contracts/      # v2.2 pydantic: node/graph_state/lifecycle, 부모 규칙, 관계, Change Plan, DTO, lineage
│   ├── storage/        # SQLAlchemy 모델 + alembic 마이그레이션 (정본 PG)
│   ├── validation/     # 서버 하드 검증 9규칙 (PoC v3_runner 규칙 수확·재작성)
│   ├── pipeline/       # apply 경로: 멱등성 → 검증 → Plan → 원자 반영(+optimistic lock)
│   ├── retrieval/      # 검색기 설정 스텁만 (M1 구현 없음)
│   └── config/         # 설정 로딩 + categories.json (설정 기반 카테고리)
├── prompts/            # PoC 복사본 (v2.2 재작성 대상 — M2)
├── evaluation/poc_frozen/  # 채점기·gold 5회의·라벨링 가이드 (동결 원본, 참조 전용)
├── tests/              # 단위 + 가짜 JSON E2E
├── alembic.ini, docker-compose.yml, .env.example, .gitlab-ci.yml
```

## 검증 9규칙 (validation/ + pipeline/)
| # | 규칙 | 위치 |
| --- | --- | --- |
| 1 | itemId 유일성 (중복 → 응답 무효, 전부 MINUTES_ONLY) | `validation/judgments.py` |
| 2 | 후보 allowlist (기존 노드 참조는 후보 목록에만) | `validation/judgments.py` |
| 3 | 부모 유효성 (Decision root / Action→Decision / Issue→Decision·Action) | `contracts/enums.py`, `validation/judgments.py` |
| 4 | evidence (segmentId 실존 + 부분 문자열 + 최소 10자 + 오프셋 역산) | `validation/evidence.py` |
| 5 | lifecycle 전이표 — 상태 세탁 차단 (COMPLETED/CANCELLED terminal) | `contracts/enums.py` |
| 6 | 순차 적용 (정렬 키 evidence 최초 startMs→segmentId→itemId, LLM 배열 순서 금지) | `validation/judgments.py`, `contracts/change_plan.py` |
| 7 | 기술적 중복 사전 감지 (UNIQUE 자연키 + 제목·근거 시그니처) | `pipeline/apply.py` |
| 8 | Change Plan 원자 적용 (부분 성공 없음, 실패 시 전체 롤백) | `pipeline/apply.py`, `service.py` |
| 9 | optimistic lock (version 불일치 → STALE, Plan 재생성 경로) | `pipeline/apply.py` |

원칙: **잘못된 그래프 반영이 누락보다 나쁘다** → 애매하면 MINUTES_ONLY 강등.

## 카테고리 값 교체 (§T 미확정)
카테고리는 하드코딩 enum 이 아니라 **설정 기반**이다. 값 교체 = ① `data_pipeline/config/categories.json`
수정 ② 재시딩 마이그레이션 1개 추가(`storage/categories.py:reseed_categories`). node.category 는
`category` reference 테이블을 FK 로 참조하고, 활성 집합 강제는 validation 레이어가 한다.
증명: `tests/test_category_swap.py`.

## M2 — 프롬프트 재작성 + ①② 연결 (회의 내 전용)
- **범위 경계**(킥오프 §2): M2 ②는 **회의 내 처리만**. 기존 결정 검색·연결(follows)·기존 액션
  UPDATE·same/reverses/resolved_by 는 M3. 그래서 ② 입력에 candidates 가 없다.
- **판정 공간**: NEW_DECISION / ATTACH(이번 회의 itemId만) / UNATTACHED(NO_RELATED_DECISION | NOT_CONFIRMED).
  PoC 의 MINUTES_ONLY 개념은 **graph_state=UNATTACHED 노드 보존**으로 구현(버리지 않음 — 재판정 대상).
- **프롬프트**: `data_pipeline/prompts/`(정본 템플릿+sha), PoC↔M2 규칙 대응은 `prompts/RULE_MAP.md`.
  granularity 규칙은 이식하지 않음(폐기 실험). R8 은 §T-1 대기 중이라 현행 유지.
- **체인**: `data_pipeline/pipeline/chain.py` — 세그먼트 → ① → itemId 유일성/evidence 검증 → ②(후보 없음)
  → M1 apply 경로 재사용 → PG. ①/② 프롬프트·raw·sha·토큰·lineage 를 `outputs/<run>/<meeting>/` 에 저장.
- **LLM 어댑터**: `data_pipeline/llm/` (GMS OpenAI 호환, gpt-5.2, json_object, timeout 180s, retry 2).
  키는 `.env`(GMS_KEY)로만. 오프라인 테스트는 FakeClient — openai 미설치여도 green.
- **회귀**: `scripts/run_m2_regression.py` (gold 5회의). gold 어댑터가 회의 간 판정(ATTACH D-*/A-*, UPDATE_ACTION)을
  **UNATTACHED 기대값으로 변환**(gold 원본 무수정, `evaluation/gold_adapter.py`). 지표는 `docs/M2_REPORT.md`.
- **실행**:
  ```bash
  # 오프라인 (LLM 없이) — 체인/어댑터 로직 검증
  pytest
  # 실 LLM 회귀 (크레딧 소비, .env 의 GMS_KEY 필요)
  python scripts/run_m2_regression.py --meetings M2X,M2Y,M1,M2,M3 --max-credits 8000 \
    --env-file /path/to/.env
  ```

## 설계 문서(kickoff v2.1 + v2.2) 대조 상태
설계 문서를 확보해 M1 스코프 항목을 전부 대조 반영했다.
- **일치**: D1′ 상태 모델 분리, §3 부모 규칙, §2 UNIQUE 키, D1‴ parent_id 단일 진실,
  D2′ Plan 원자 적용, M4 관계 모델(SAME/REVERSES/FOLLOWS/RESOLVED_BY × PROPOSED/CONFIRMED/REJECTED),
  §5 단순화(command 테이블 없음·advisory lock 없음·범용 outbox·임베딩 v1 고정), 검색 설정값 분리.
- **문서에 맞춰 정정**: R4′ node_embedding PK(node_id, embedding_version)+embedded_text_hash/status,
  D1″ transcript_segment(sequence_no·text_hash) / node_evidence(quote_start·quote_end·evidence_type·source_meeting_id),
  §5 outbox 타입(EMBEDDING_REQUESTED / MEETING_PROCESSING_COMPLETED / GRAPH_CHANGED),
  M4 재제안 억제 키 컬럼(from/to_content_hash·merge_rule_version, 로직은 병합 코드와 함께 후속).
- **§T 미확정으로 보류**: 카테고리 최종 enum(§T-2) — 리뷰어 권장안은 `DATA` 포함(PLANNING/DESIGN/
  FRONTEND/BACKEND/AI/INFRA/**DATA**/ETC)이나 현재 config 기본값은 작업 지시 임시값 7종. 확정 시
  `categories.json` + 재시딩 1개로 반영(§T-2 승인 대기). follows 자동화·R8 등 나머지 §T 블로커는 M2+.
