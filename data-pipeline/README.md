# data-pipeline

## STT 정규화 연결 흐름

`run_meeting()`에 들어온 세그먼트의 `text`를 원문(`rawText`)으로 보존한 뒤,
`normalization/stt_terms.json`과 규칙으로 `normalizedText`를 만든다.
LLM 추출·판단 및 evidence 검증에는 정규화된 `text`를 사용하고, PostgreSQL에는
원문·정규화문·적용 규칙/위치·사전 버전/SHA-256을 함께 저장한다. 같은 입력의 중복 실행
판별 해시에도 동일한 정규화 결과와 사전 정보를 포함한다.

## Candidate 1차 검토 경계

신규 흐름에서는 `complete_initial_review()`가 Candidate의 사용자 검토값으로
`graph_state=UNATTACHED`, `analysis_status=PENDING` Node와 Evidence만 생성한다.
LLM이 추천한 부모가 있더라도 이 단계에서는 `parent_id`나 Relation을 만들지 않는다.
`approve_candidate()`와 `bulk_approve_candidates()`는 기존 호출자 호환용 경로이며,
신규 흐름은 최종 승인 API가 구현될 때까지 이를 사용하지 않는다.

## UNATTACHED Node 수정과 분석 무효화

`edit_unattached_node()`는 최종 승인 전인 `UNATTACHED` Node의 유형·카테고리·제목·본문·Evidence를
수정한다. 실제 값이 바뀌면 Node `version`을 1 증가시키고 `analysis_status=STALE`,
`analysis_input_hash=NULL`로 만들어 이전 Retrieval/B 모델 결과를 더 이상 사용할 수 없게 한다.
같은 수정 요청의 재전송은 값을 중복 변경하지 않으며, 다른 수정과 버전이 충돌하면 실패한다.

Evidence에는 원문 위치와 출처로 계산한 안정적인 `evidence_key`를 저장한다.
`(node_id, evidence_key)` UNIQUE 제약과 UPSERT를 함께 사용하므로 같은 Evidence를 다시 저장해도
중복 레코드가 생기지 않는다. `NodeEvidence.source_candidate_id`는 추가하지 않고 Node와 Candidate의
기존 연결로 출처를 추적한다.

## 분석 실행 경계

`reanalyze_unattached_node()`는 현재 Node version과 결정적으로 계산한 `analysis_input_hash`를 기준으로
분석 실행을 생성한다. 이 함수는 실제 Retrieval이나 B 모델을 호출하지 않는다.

```text
Node: PENDING → ANALYZING → ANALYZED
Run:  PENDING → RUNNING   → COMPLETED
```

실패한 실행은 `FAILED`로 보존하고 다음 요청에서 attempt를 증가시킨다. 같은 입력의 PENDING,
RUNNING 또는 COMPLETED 실행은 새로 만들지 않고 멱등 반환한다. 입력이 수정되면 기존 실행은
`SUPERSEDED`, Node는 `STALE`이 된다. 분석 상태만 변경할 때는 Node `version`이 증가하지 않는다.

PostgreSQL은 부분 UNIQUE 인덱스로 같은 Node·입력 해시의 활성 Run을 하나로 제한한다.
복합 FK는 `current_analysis_run_id`가 다른 Node의 Run을 가리키지 못하게 하고, Retrieval target
version은 1 이상만 허용한다. 분석 해시 v2에는 `retrieval_config_version`과 별도로 임베딩
모델·버전도 포함한다. `retrieval_config_version`은 거리 계산법·Top-K·필터·정렬 정책이 바뀔 때
반드시 증가시킨다.

노드 생성 파이프라인. **토폴로지 A**: 그래프 **정본(source of truth)은 이 파이썬 프로젝트가
소유하는 PostgreSQL** 이다. 스프링(`../Backend/`)은 이 그래프 DB 에 **직접 접근하지 않고**,
파이프라인이 발행하는 범용 `outbox_event` 및 API/메시지로만 통신한다(연동 자체는 M4).

> ⚠️ **그래프 정본 = 이 PG. 스프링 직접 접근 금지.** 스키마 변경·쓰기는 이 프로젝트의 alembic
> 마이그레이션·apply 경로를 통해서만 이뤄진다.

## 현재 구현 범위

- Extraction + Judgment LLM 체인(실행 profile을 명시적으로 선택)
- LLM 호출 전 generation request 선점과 중복 호출 차단
- raw 응답, prompt lineage, token/credit/latency, 실패 stage 저장
- 모든 extraction item을 사용자 검토용 `NodeCandidate`로 보존
- 후보 목록/상세/수정/거절, candidate `version` 기반 낙관적 락, 감사 로그
- 1차 검토 완료 시 UNATTACHED Node와 중복 방지 Evidence 생성
- UNATTACHED Node 수정, 낙관적 락, 이전 분석 무효화
- 분석 실행 요청·선점·완료·실패 상태 전이와 실행 이력 저장
- Alembic schema, PostgreSQL 16 + pgvector, SQLite 오프라인 테스트 호환

아직 구현되지 않은 범위:

- embedding worker와 Top-K retrieval
- B 모델 기반 기존 Node 병합 추천
- 기존 Node 병합 최종 승인
- HTTP/API 및 Spring 연동

## 환경변수와 로컬 파일

`.env.example`은 이름과 개발 기본값을 공유하는 문서다. 실제 `.env`와 `.env.*`는 Git에서 제외된다.

- DB/카테고리/Retrieval 설정은 `data_pipeline.config`가 **현재 프로세스의 환경변수**에서 읽는다.
  `.env`를 자동으로 읽지 않는다.
- DB URL을 지정하지 않으면 로컬 Compose와 같은
  `postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline`을 기본값으로 사용한다.
- 실 LLM 실행만 `--env-file .env`를 전달해 `GMS_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`을 읽는다.
- 오프라인 테스트와 migration 확인에는 `GMS_KEY`가 필요하지 않다.
- `CATEGORY_CONFIG_PATH`를 지정하지 않으면 버전 관리되는
  `data_pipeline/config/categories.json`을 사용한다.
- `.venv/`, `outputs/`, 로컬 SQLite 파일도 Git에서 제외된다.

API 키가 필요할 때만 `.env.example`을 `.env`로 복사하고 `GMS_KEY`를 직접 입력한다. `.env`를
커밋하거나 로그에 출력하지 않는다.

## 빠른 시작: Windows PowerShell + 정본 PostgreSQL

CI는 Python 3.12를 사용한다. Python 3.11 이상을 지원하며, 2026-07-30에 Windows Python 3.13에서도
아래 절차와 오프라인 전체 테스트를 확인했다.

```powershell
cd C:\path\to\S15P11D205\data-pipeline

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

docker compose up -d
docker compose ps
docker compose exec -T postgres pg_isready -U pipeline -d pipeline

$env:DATABASE_URL = "postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current

.\.venv\Scripts\python.exe -m pytest -q
```

`docker compose ps`가 `healthy`, `alembic current`가 `0003_review_analysis (head)`인지 확인한다.

`docker compose up`만 사용하고 `Ctrl+C`를 누르면 PostgreSQL도 정지한다. 개발 중에는
`docker compose up -d`로 백그라운드 실행한다. `docker compose down`은 컨테이너/네트워크만
정리하고 DB volume은 유지한다. `docker compose down -v`는 DB 데이터까지 삭제하므로 초기화가
필요할 때만 사용한다.

## 빠른 시작: macOS/Linux

```bash
cd /path/to/S15P11D205/data-pipeline

python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

docker compose up -d
export DATABASE_URL=postgresql+psycopg://pipeline:pipeline@localhost:5432/pipeline
alembic upgrade head
alembic current
python -m pytest -q
```

## Docker 없이 실행하는 오프라인 테스트

기본 테스트는 실제 LLM을 호출하지 않고, 테스트별 임시 SQLite 파일에 Alembic head를 적용한다.
따라서 PostgreSQL과 `GMS_KEY` 없이도 실행할 수 있다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

2026-07-30 오프라인 검증 결과는 `163 passed, 1 skipped`다. 폐기 가능한 임시 PostgreSQL DB를
생성해 `TEST_POSTGRESQL_URL`로 전달한 전체 검증에서는 migration downgrade/upgrade 왕복까지
포함해 `164 passed`를 확인했다. 일반 개발 DB인 `pipeline`을 `TEST_POSTGRESQL_URL`로 지정하지 않는다.

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
  → 모든 item을 `NodeCandidate`로 PG에 저장한다. 사용자 승인 전에는 정식 Node/Relation/NodeEvidence를
  만들지 않는다. ①/② 프롬프트·raw·sha·토큰·lineage는 선택적으로 `outputs/<run>/<meeting>/`에 저장한다.
- **LLM 어댑터**: `data_pipeline/llm/` (GMS OpenAI 호환, gpt-5.2, json_object, timeout 180s, retry 2).
  키는 `.env`(GMS_KEY)로만. 오프라인 테스트는 FakeClient — openai 미설치여도 green.
- **회귀**: `scripts/run_m2_regression.py` (gold 5회의). gold 어댑터가 회의 간 판정(ATTACH D-*/A-*, UPDATE_ACTION)을
  **UNATTACHED 기대값으로 변환**한다(gold 원본 무수정, `evaluation/gold_adapter.py`). 회귀 결과는
  Git에 커밋하지 않는 `outputs/`에 기록한다.
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
