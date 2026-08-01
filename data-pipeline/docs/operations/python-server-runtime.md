# Python 서버 실행 및 배포

프로세스는 **4개**이며 각각 독립적으로 기동/중지된다.

```text
python -m data_pipeline.worker             # OpenVidu/S3 SQS 수집 워커
python -m data_pipeline.api                # 검토 REST API (FastAPI)
python -m data_pipeline.analysis_worker    # 임베딩·Retrieval·B 모델
python -m data_pipeline.outbox_publisher   # Outbox relay
```

네 프로세스는 같은 PostgreSQL을 공유한다. API와 워커는 서로를 HTTP로 호출하지 않는다.

---

## 1. 설치

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

| extra | 포함 |
|---|---|
| `api` | fastapi, uvicorn |
| `llm` | openai |
| `dev` | pytest + 위 전부 |

워커만 돌릴 서버라면 `api` extra는 필요 없다.

---

## 2. DB 마이그레이션

```powershell
.venv\Scripts\python.exe -m alembic upgrade head   # 현재 head: 0004_runtime_pipeline
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check
```

> **주의**: `alembic_version.version_num`은 `varchar(32)`다. 새 revision id는
> **32자 이하**여야 한다. SQLite는 길이를 강제하지 않아 테스트에서 잡히지 않는다.

pgvector 확장이 필요하다.
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 3. FastAPI

```powershell
python -m data_pipeline.api
```
내부적으로 uvicorn을 기동한다. 직접 실행도 가능하다.
```powershell
.venv\Scripts\python.exe -m uvicorn data_pipeline.api.app:app --host 0.0.0.0 --port 8000
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `API_HOST` | `127.0.0.1` | 컨테이너에서는 `0.0.0.0` |
| `API_PORT` | `8000` | |
| `API_RELOAD` | (off) | 개발용만 |
| `API_MAX_REQUEST_BODY_BYTES` | `1048576` | Content-Length·chunked body 공통 제한 |
| `API_GRACEFUL_SHUTDOWN_SECONDS` | `20` | 진행 중 요청 대기 |
| `LOG_LEVEL` | `INFO` | |

### Health check

| 경로 | 용도 |
|---|---|
| `GET /health/live` | liveness probe. 프로세스 생존만 |
| `GET /health/ready` | 설정 + DB 연결 + Alembic head 일치. 실패 시 **503** |

`ready`는 Clova/LLM/임베딩 provider를 호출하지 않는다.

### DB pool / graceful shutdown

- 엔진은 프로세스당 1개 싱글턴이며 API와 Worker가 같은 pool 정책을 사용한다.
- `pool_pre_ping`을 사용하고 pool 크기·대기시간·재활용·연결 timeout·statement timeout을
  환경변수로 제한한다.
- lifespan 종료 시 `dispose_engine()`이 pool을 반납한다.
- uvicorn `timeout_graceful_shutdown` 동안 진행 중 요청이 끝날 시간을 준다.

| 환경변수 | 기본값 |
|---|---:|
| `DB_POOL_SIZE` | `5` |
| `DB_MAX_OVERFLOW` | `5` |
| `DB_POOL_TIMEOUT_SECONDS` | `30` |
| `DB_POOL_RECYCLE_SECONDS` | `1800` |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` |
| `DB_STATEMENT_TIMEOUT_MS` | `30000` |

API는 모든 응답에 `X-Request-Id`를 반환한다. Spring이 128자 이하의 안전한
`X-Request-Id`를 보내면 그대로 사용하고, 없거나 잘못된 값이면 UUID를 생성한다.
제목 300자, 본문 20,000자, 1회 초기 검토 Candidate 200개를 상한으로 둔다.

### OpenAPI
`GET /openapi.json`, `GET /docs`

**인증이 없다.** 내부망 전용으로 배치할 것. 상세는
[`python-review-api-contract.md`](../contracts/python-review-api-contract.md).

---

## 4. OpenVidu / S3 SQS 워커

```powershell
python -m data_pipeline.worker
```
설정은
[`openvidu-egress-worker-contract.md`](../contracts/openvidu-egress-worker-contract.md),
[`openvidu-egress-aws-requirements.md`](./openvidu-egress-aws-requirements.md) 참조.

---

## 5. Analysis Worker

```powershell
python -m data_pipeline.analysis_worker
```

`analysis_job`을 폴링해 임베딩 → pgvector Retrieval → B 모델을 실행한다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `EMBEDDING_ADAPTER` | `fake` | 실제 호출은 `gms` (또는 `openai`) |
| `EMBEDDING_BASE_URL` | `OPENAI_BASE_URL` | OpenAI 호환 게이트웨이 |
| `EMBEDDING_MODEL` | `RETRIEVAL_EMBEDDING_MODEL` | 기본 `text-embedding-3-small` |
| `EMBEDDING_TIMEOUT_SECONDS` | `60` | |
| `EMBEDDING_RETRY_COUNT` | `2` | |
| `EMBEDDING_RETRY_BACKOFF_SECONDS` | `0.5` | |
| `GMS_KEY` | — | **필수**. 로그에 절대 남기지 않는다 |
| `B_MODEL_ADAPTER` | — | `gms` 또는 `openai`; 미지정 시 기동 실패 |
| `B_MODEL_API_KEY` | `GMS_KEY` | |
| `B_MODEL_BASE_URL` | `OPENAI_BASE_URL` | |
| `B_MODEL_NAME` | `OPENAI_MODEL` | |
| `B_MODEL_TIMEOUT_SECONDS` | `120` | |
| `ANALYSIS_IDLE_SLEEP_SECONDS` | `2` | 큐가 비었을 때 |

`GmsBModelClient`와 `GmsEmbeddingClient`가 구현되어 있다. 실제 Analysis Worker는
`EMBEDDING_ADAPTER=gms`, `B_MODEL_ADAPTER=gms` 및 credential을 설정해야 한다.
테스트는 외부 호출 대신 주입한 Fake client를 사용한다.

동시성: 여러 인스턴스를 띄워도 안전하다 (PostgreSQL `FOR UPDATE SKIP LOCKED`).
재시작 복구: `RUNNING`인 채 죽은 job은 claim timeout(기본 1800초) 후 회수된다.
재시도: 실패 시 지수 backoff, `max_attempts`(기본 3) 초과 시 `FAILED` + `PIPELINE_FAILED` 이벤트.

---

## 6. Outbox Publisher

```powershell
python -m data_pipeline.outbox_publisher
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `OUTBOX_TRANSPORT` | `fake` | `fake` \| `http` |
| `OUTBOX_HTTP_ENDPOINT` | — | `http`일 때 필수 |
| `OUTBOX_HTTP_AUTH_HEADER` | — | 선택 |
| `OUTBOX_HTTP_TIMEOUT_SECONDS` | `10` | |
| `OUTBOX_BATCH_SIZE` | `20` | |
| `OUTBOX_STALL_TIMEOUT_SECONDS` | `300` | 죽은 publisher 선점 회수 |
| `OUTBOX_IDLE_SLEEP_SECONDS` | `2` | |

여러 인스턴스 동시 실행 가능. 상세는
[`python-outbox-event-contract.md`](../contracts/python-outbox-event-contract.md).

---

## 7. 공통 환경변수

```env
DATABASE_URL=postgresql+psycopg://pipeline:***@localhost:5432/pipeline
ENV_FILE=.env
LOG_LEVEL=INFO

RETRIEVAL_EMBEDDING_MODEL=text-embedding-3-small
RETRIEVAL_EMBEDDING_VERSION=v1
RETRIEVAL_EMBEDDING_DIM=1536
RETRIEVAL_NODE_TOP_K=5
RETRIEVAL_MIN_SIMILARITY=
```

비밀값(`GMS_KEY`, `CLOVA_SECRET`, DB 비밀번호, AWS 키)은 `.env`로만 주입하며
**커밋하지 않는다.** 로그에도 남기지 않는다.

---

## 8. docker-compose

현재 `docker-compose.yml`은 로컬 PostgreSQL(pgvector/pg16)만 정의한다.
애플리케이션 서비스는 아직 없다. 추가한다면 위 4개 프로세스를 각각의 서비스로 두고,
같은 `DATABASE_URL`과 `.env`를 공유하면 된다. 기존 파일은 이번 작업에서 변경하지 않았다.

---

## 9. 실행 순서

```text
1. PostgreSQL 기동 + CREATE EXTENSION vector
2. alembic upgrade head
3. python -m data_pipeline.api                (검토 화면용)
4. python -m data_pipeline.worker             (음성 수집)
5. python -m data_pipeline.analysis_worker    (Embedding/B 모델 설정 후)
6. python -m data_pipeline.outbox_publisher   (Spring 수신 방식 확정 후)
```

3·4는 설정 후 실행 가능하다. 5는 실제 Embedding/B 모델 credential이 필요하고,
6은 Spring 수신 계약이 필요하다.

---

## 10. 성능 메모 — pgvector 인덱스

현재 Retrieval은 **exact cosine search**다 (`ORDER BY ne.embedding <=> ...`).
`node_embedding`에 HNSW/IVFFlat 인덱스가 **없다.**

- Node 수가 프로젝트당 수백~수천 규모면 순차 스캔으로 충분하다.
  실측: 3개 Node에서 정상 동작, 의미상 가장 가까운 Node가 1위(0.781) / 무관한 Node(0.442).
- **수만 건을 넘어가면** 지연이 선형으로 증가한다. 그때 아래를 추가한다.
  ```sql
  CREATE INDEX ON node_embedding
    USING hnsw (embedding vector_cosine_ops);
  ```
  `<=>`(cosine distance)를 쓰므로 연산자 클래스는 `vector_cosine_ops`여야 한다.
- 인덱스는 근사 검색이므로 recall이 100%가 아니다. 도입 시 top-k 품질을 재측정할 것.
- 이번 범위에서는 추가하지 않았다 (규모가 작고, 근사 검색 도입은 품질 영향이 있음).
