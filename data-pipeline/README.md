# data-pipeline

## Java Command · OpenVidu Recording Join (현재 제품 경로)

현재 제품 경로는 녹화 완료 SQS를 잡은 채 STT/LLM을 실행하지 않는다. 두 짧은 consumer가 입력을 PostgreSQL에 commit한 뒤 ACK하고, 별도 coordinator가 `(projectId, roomName)`으로 Java command와 recording을 join한다.

```text
Recording Ready SQS ─→ recording-ready-consumer ─┐
                                                 ├→ DB join → coordinator
Java Command SQS ────→ analysis-command-consumer ┘            ├→ SUMMARY
                                                              └→ NODES
NODES 성공 → Full Snapshot v1 → S3 → Result Event v3(snapshotRef) → Java
SUMMARY 성공 → Java meeting-record HTTP Callback → Java
```

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m data_pipeline.meeting_analysis recording-ready-consumer
.\.venv\Scripts\python.exe -m data_pipeline.meeting_analysis analysis-command-consumer
.\.venv\Scripts\python.exe -m data_pipeline.meeting_analysis coordinator
.\.venv\Scripts\python.exe -m data_pipeline.outbox_publisher
```

필수 설정은 `RECORDING_READY_QUEUE_URL`, `ANALYSIS_COMMAND_QUEUE_URL`, `OPENVIDU_RECORDING_BUCKET`, `PROJECTREE_ANALYSIS_RESULT_QUEUE_URL`, `AWS_S3_BUCKET`, `PROJECTREE_GRAPH_SNAPSHOT_PREFIX`, `PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES=10485760`, `JAVA_BASE_URL`, `MEETING_RECORD_CALLBACK_API_KEY`, `MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS`와 공통 AWS/DB 설정이다. Snapshot 제한은 Java의 10 MiB(`10,485,760` bytes)와 같으며 실제 S3에 올릴 canonical UTF-8 JSON byte 배열에 적용한다. OpenVidu Recording Queue, Java Command Queue, Java Result Queue는 역할이 다른 별도 Queue다. `OUTBOX_TRANSPORT=result-sqs`는 v3 row만 발행한다. Legacy OpenVidu 장시간 Worker와 수동 merge API는 각각 `ENABLE_LEGACY_OPENVIDU_AUDIO_WORKER`, `ENABLE_LEGACY_MANUAL_MERGE_API`를 명시하지 않으면 비활성이다.

SUMMARY와 NODES는 STT 결과만 공유하고 동시에 실행되는 독립 작업이다. Java command의 `generateSummary`, `generateNodes`가 각각 task 생성을 결정한다. SUMMARY 성공은 Java HTTP Callback, NODES 성공은 `PROJECT_GRAPH_CHANGED`, 최종 실패는 task별 `ANALYSIS_TASK_STATUS_CHANGED`로 통지하며 통합 성공 barrier는 사용하지 않는다. 상세 계약은 [Command Join v1](docs/contracts/meeting-analysis-command-join-v1.md), [Result Event v3](docs/contracts/java-result-event-v3.md), [자동 흡수 병합](docs/contracts/automatic-node-merge.md), [Meeting Summary](docs/contracts/meeting-summary-contract.md)을 따른다.

같은 `ANALYSIS_COMMAND_QUEUE_URL`은 저장 완료된 canonical Node의 사용자 사후 수정
`NODE_CONTENT_UPDATE_REQUESTED`도 받는다. 이 명령은 회의 recording join이나 LLM을
실행하지 않고 Node row lock, USER Revision, Embedding/Analysis 무효화, graphVersion,
Full Snapshot Artifact와 Result v3 Outbox를 한 트랜잭션으로 반영한다. 성공 Result는
`PROJECT_GRAPH_CHANGED`, `sourceType=NODE_CONTENT_UPDATE`, top-level
`meetingId=null`이다. 상세 계약은 [Node Content Update Command v1](docs/contracts/node-content-update-command-v1.md)을 따른다.

`SUMMARY_ADAPTER=gms`는 기존 OpenAI 호환 GMS Client를 사용해 `title`, `summary`, `decisions`, `nextTodos`, `issues`의 엄격한 JSON 계약을 생성한다. `fake`는 `tests/config/fake/`에서만 허용되며 production coordinator는 모든 Fake AI adapter를 시작 단계에서 거부한다. `NO_EXTERNAL_AI_CALLS=1`이면 GMS Client 생성 전에 차단되므로 기본 테스트는 크레딧을 사용하지 않는다.

## Clova STT 어댑터

`data_pipeline.stt.Transcriber`는 로컬 음성 `Path`와 `meeting_id`를 받아
`run_meeting()`의 `meeting_input["segments"]`에 바로 넣을 수 있는 세그먼트
목록을 반환한다. 현재 선택지는 `STT_ADAPTER=fake|clova`이다.

- `fake`: 외부 API를 호출하지 않는다. `STT_FAKE_RESPONSE_PATH`의 JSON
  fixture를 사용하며, 경로를 비우면 S3/SQS 연결 점검용 기본 응답을 사용한다.
- `clova`: 기존 Clova Speech 동기 업로드 계약을 사용한다.
  `CLOVA_INVOKE_URL`, `CLOVA_SECRET`이 반드시 필요하다.

```python
from pathlib import Path

from data_pipeline.config import load_settings
from data_pipeline.stt import build_transcriber

settings = load_settings()
transcriber = build_transcriber(settings.stt)
segments = transcriber.transcribe(
    Path("meeting.wav"),
    meeting_id="meeting-001",
)
meeting_input = {
    "projectId": "project-uuid",
    "externalMeetingId": "meeting-001",
    "segments": segments,
}
```

테스트는 작은 Clova 응답 fixture와 주입한 mock HTTP client만 사용하며 실제
Clova API를 호출하지 않는다.

## S3·SQS 음성 Worker

입력 object key 계약은 다음과 같다.

```text
audio-input/{project_id}/{external_meeting_id}/{upload_id}/{filename}
```

Worker는 SQS를 한 메시지씩 long polling하고, S3 `ObjectCreated` Record를 모두
검증한 다음 아래 순서로 처리한다.

```text
SQS 수신
→ bucket/key/versionId 또는 eTag 멱등 claim
→ S3 임시 다운로드
→ Transcriber
→ run_meeting() Candidate 생성
→ Decision-first Embedding/Retrieval/B 모델
→ 원자적 Graph Mutation Plan 반영
→ audio_upload_event COMPLETED
→ SQS DeleteMessage
```

한 SQS 메시지에 여러 Record가 있으면 모두 성공한 경우에만 메시지를 삭제한다.
중간 Record가 실패하면 앞서 완료된 Record는 DB에 보존되고, 메시지 재수신 시
완료된 Record는 건너뛰고 실패한 Record만 재시도한다. 임시 음성 파일은 성공과
실패 모두 삭제된다.

첫 통합 점검에서는 실제 Clova·LLM·Embedding API를 사용하지 않는다.

```powershell
$env:APP_ENV = "test"
$env:STT_ADAPTER = "fake"
$env:LLM_ADAPTER = "fake"
$env:EMBEDDING_ADAPTER = "fake"
$env:B_MODEL_ADAPTER = "fake"
$env:AWS_REGION = "ap-northeast-2"
$env:SQS_QUEUE_URL = "<test queue URL>"
$env:S3_ALLOWED_BUCKETS = "<test bucket name>"
$env:DATABASE_URL = "<disposable PostgreSQL URL>"

.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m data_pipeline.worker
```

AWS SDK는 기본 credential chain을 사용한다. 환경값이 없을 때 운영 리소스를
추측하지 않으며, Worker 시작 전에 `AWS_REGION`, `SQS_QUEUE_URL`,
`S3_ALLOWED_BUCKETS`를 모두 요구한다. 필요한 최소 권한은 테스트 prefix의
`s3:GetObject`, 테스트 Queue의 `sqs:ReceiveMessage`,
`sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`,
`sqs:GetQueueAttributes`이다.

## STT 정규화 연결 흐름

`run_meeting()`에 들어온 세그먼트의 `text`를 원문(`rawText`)으로 보존한 뒤,
`normalization/stt_terms.json`과 규칙으로 `normalizedText`를 만든다.
LLM 추출·판단 및 evidence 검증에는 정규화된 `text`를 사용하고, PostgreSQL에는
원문·정규화문·적용 규칙/위치·사전 버전/SHA-256을 함께 저장한다. 같은 입력의 중복 실행
판별 해시에도 동일한 정규화 결과와 사전 정보를 포함한다.

## 현재 제품 흐름: 자동 Node 생성·연결·병합

SQS Worker는 A 모델 Candidate를 추적 데이터로 보존한 뒤 사용자 승인 API를
기다리지 않고 자동 Graph Plan을 실행한다.

```text
Evidence 서버 검증
→ Decision 우선 분석 및 canonical 확정
→ Action/Issue 분석과 부모 해석
→ MERGE 안전 게이트 및 target version 재검사
→ Node + Revision + Evidence + Relation + MergeOperation 원자 반영
→ GRAPH_GENERATION_COMPLETED Outbox
```

정상 배치된 Node는 `ACTIVE`이며, 유효한 구조 부모를 찾지 못한 Action/Issue만
`UNATTACHED`다. 병합은 source 원본과 Relation endpoint를 보존하는 논리
병합이며 조회 때 canonical endpoint를 계산한다. 운영 MERGE 임계값이 비어 있으면
MERGE만 `CREATE_NEW`로 안전하게 강등된다. 상세 계약은
[`docs/contracts/automatic-node-merge.md`](docs/contracts/automatic-node-merge.md)다.

FastAPI 제품 경로는 그래프 조회·사용자 직접 편집·논리 병합/해제다. 사용자
편집은 새 Revision을 만들며 LLM을 다시 호출하지 않는다. 운영/스테이징에서는
`INTERNAL_API_TOKEN`이 필수이고 기존 Candidate 승인 API는 기본 비활성이다.

## 회의록 정본과 조회

회의록 본문은 그래프 실행 통계인 `GenerationRun.result_summary`와 분리된
`meeting_summary`에 versioned immutable 문서로 먼저 저장한다. Command 기반 제품
경로는 저장된 결과를 Java meeting-record HTTP Callback으로 전달하며, Java의 200 응답
이후에만 SUMMARY task를 성공 처리한다. Callback 재실행은 저장된 결과를 재사용한다.
Command가 없는 legacy 경로만 `MEETING_SUMMARY_READY` Outbox와
`GET /api/v1/meetings/{meetingId}/summary` 조회를 유지한다. 실제 제품 경로는
`GmsMeetingSummaryGenerator`, 테스트 경로는 deterministic
`FakeMeetingSummaryGenerator`를 사용한다. 기본 검증에서는 실제 GMS 호출이
안전 스위치로 차단된다. 상세 계약은
[`docs/contracts/meeting-summary-contract.md`](docs/contracts/meeting-summary-contract.md)다.

## 레거시 호환: Candidate 1차 검토 경계

아래 흐름은 이전 호출자 전환과 회귀 테스트를 위해 유지하는 호환 경로다. 자동
SQS 제품 흐름에서는 호출하지 않는다.

신규 흐름에서는 `complete_initial_review()`가 Candidate의 사용자 검토값으로
`graph_state=UNATTACHED`, `analysis_status=PENDING` Node와 Evidence만 생성한다.
LLM이 추천한 부모가 있더라도 이 단계에서는 `parent_id`나 Relation을 만들지 않는다.
확정 계약은 [`docs/CANDIDATE_NODE_CONFIRMATION_CONTRACT.md`](docs/CANDIDATE_NODE_CONFIRMATION_CONTRACT.md)에
정리되어 있다.

분석 Job은 Decision-first 순서로 해제된다.

```text
1차 검토 완료
→ Decision이 있으면 Decision만 analysis_job 등록
→ 모든 Decision이 사용자 최종 결정(ACTIVE 또는 MERGED)
→ 같은 meeting의 대기 중 Action/Issue analysis_job 등록

Decision이 없는 meeting
→ Action/Issue analysis_job 즉시 등록
```

마지막 Decision의 기존 추천 승인 API와 사용자 직접 결정 API 모두 같은
`release_pending_dependent_nodes_if_ready()` 후처리를 사용한다. Decision이
MERGE되면 같은 회의의 부모 hint는 `merged_into_node_id` 계보를 따라 최종
canonical Node를 사용한다.

기존 `process_request()`, `apply_change_plan()`, `approve_candidate()`,
`bulk_approve_candidates()`는 ACTIVE Node나 Relation을 직접 만들 수 있으므로 기본 실행이
차단되어 있다. 과거 동작의 회귀 테스트에서만 pytest 실행 중 전용 환경변수로 열 수 있으며,
신규 애플리케이션 코드에서는 이 경로를 호출하지 않는다.

## 레거시 호환: UNATTACHED Node 수정과 분석 무효화

`edit_unattached_node()`는 최종 승인 전인 `UNATTACHED` Node의 유형·카테고리·제목·본문·Evidence를
수정한다. 실제 값이 바뀌면 Node `version`을 1 증가시키고 `analysis_status=STALE`,
`analysis_input_hash=NULL`로 만들어 이전 Retrieval/B 모델 결과를 더 이상 사용할 수 없게 한다.
같은 수정 요청의 재전송은 값을 중복 변경하지 않으며, 다른 수정과 버전이 충돌하면 실패한다.

Evidence에는 원문 위치와 출처로 계산한 안정적인 `evidence_key`를 저장한다.
`(node_id, evidence_key)` UNIQUE 제약과 UPSERT를 함께 사용하므로 같은 Evidence를 다시 저장해도
중복 레코드가 생기지 않는다. `NodeEvidence.source_candidate_id`는 추가하지 않고 Node와 Candidate의
기존 연결로 출처를 추적한다.

## 레거시 호환: 분석 실행 경계

`reanalyze_unattached_node()`는 현재 Node version과 결정적으로 계산한 `analysis_input_hash`를 기준으로
분석 실행을 생성한다. 이 함수 자체는 Embedding, Retrieval, B 모델을 호출하지 않는다.
worker 경계인 `execute_analysis_retrieval()`에 주입 가능한 Embedding client를 전달하면
Embedding 생성·저장과 pgvector Retrieval을 수행한다. Analysis Worker는
`EMBEDDING_ADAPTER=gms|openai`일 때 OpenAI 호환 Embedding API adapter를 사용한다.

```text
Node: PENDING → ANALYZING
Run:  PENDING → RUNNING
```

Embedding과 Retrieval이 성공하면 주입식 B 모델 client를 받는 `execute_b_model()`이
`CREATE_NEW`, `LINK`, `MERGE` 판단을 검증한다. 검증된 결과와 최종 승인 대기
`AnalysisCandidate`를 같은 트랜잭션에 저장한 뒤에만 Run을 `COMPLETED`, Node를 `ANALYZED`로
만든다. Retrieval이 0건이면 B 모델을 호출하지 않고 `SKIPPED /
NO_RETRIEVAL_CANDIDATES`를 기록하며 Candidate 없이 정상 완료한다.

계약 경계인 `approve_create_new()`, `approve_link_existing()`, `approve_merge_existing()`와
공통 구현 `approve_analysis_candidate()`, `reject_analysis_candidate()`는 Candidate row를 잠그고
최초의 `PENDING` 결정만 반영한다. 승인은 확정 계약의 부모 규칙에 따라 원본 UNATTACHED Node를
ACTIVE로 전환하거나, 확정 Relation을 만들거나, 기존 target Node로 병합한다. MERGE는
`node_merge_history`를 남기고 target의 READY Embedding을 STALE로 만든다. LINK처럼 embedding
입력이 바뀌지 않는 승인은 기존 READY Embedding을 유지한다. 실제 외부 B 모델 adapter와
Embedding adapter는 Analysis Worker에 연결되어 있다. 기존 ACTIVE Node 전체 backfill과
최종 승인으로 STALE이 된 target의 자동 재생성은 별도 운영 작업으로 남아 있다.

실패한 실행은 `FAILED`로 보존하고 다음 요청에서 attempt를 증가시킨다. 같은 입력의 PENDING 또는
RUNNING 실행은 새로 만들지 않고 멱등 반환한다. 입력이 수정되면 기존 실행은 `SUPERSEDED`,
Node는 `STALE`이 되고 기존 Embedding은 `STALE`이 된다. 분석 상태만 변경할 때는 Node
`version`이 증가하지 않는다.

PostgreSQL은 부분 UNIQUE 인덱스로 같은 Node·입력 해시의 활성 Run을 하나로 제한한다.
복합 FK는 `current_analysis_run_id`가 다른 Node의 Run을 가리키지 못하게 하고, Retrieval target
version은 1 이상만 허용한다. 분석 해시 v2에는 `retrieval_config_version`과 별도로 임베딩
모델·버전도 포함한다. `retrieval_config_version`은 거리 계산법·Top-K·필터·정렬 정책이 바뀔 때
반드시 증가시킨다.

Retrieval은 같은 프로젝트의 `ACTIVE + UNATTACHED` Node 중 자기 자신과 병합된 Node를 제외한다.
PostgreSQL에서는 pgvector cosine distance `<=>`의 오름차순으로 검색하고, 외부에 저장하는 값은
`1 - distance`인 similarity다. 동점은 Node UUID 오름차순으로 고정한다. Top-K와 선택적인
similarity 하한은 `RETRIEVAL_NODE_TOP_K`, `RETRIEVAL_MIN_SIMILARITY`로 설정한다.

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
- 분석 실행 요청·선점·완료 보호·실패 상태 전이와 실행 이력 저장
- 주입 가능한 Embedding 생성·저장과 동일 프로젝트 pgvector Top-K Retrieval
- 주입 가능한 B 모델 판단, 검증 결과·최종 승인 Candidate 저장
- Candidate 승인·거절과 CREATE_NEW/LINK/MERGE 원자 반영
- FastAPI 검토 API, durable Analysis Worker, Outbox Publisher
- GMS/OpenAI 호환 Embedding·B 모델 adapter
- S3 ObjectCreated → SQS → Clova/Fake STT → Candidate 생성 Worker
- Decision-first 자동 Graph Plan, immutable Revision/Evidence, 논리 MERGE/UNMERGE
- Graph 조회·사용자 직접 Node/Relation 편집 내부 API와 service token 경계
- Alembic schema, PostgreSQL 16 + pgvector, SQLite 오프라인 테스트 호환

아직 구현되지 않은 범위:

- 기존 ACTIVE Node Embedding backfill과 승인 후 자동 재생성
- Spring 인증·API 호출·Outbox 수신 구현
- OpenVidu Meeting ID 정본 및 project/meeting 매핑 확정
- EC2 배포와 프로세스 감시 구성

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

`docker compose ps`가 `healthy`,
`alembic current`가 `0010_meeting_analysis_join_v3 (head)`인지 확인한다.

실제 배포 설정 예시는 루트 `.env.example`, 외부 호출이 완전히 차단된
개발/CI 예시는 `tests/config/fake/.env.example.fake`를 사용한다. 두 파일을 섞지 않는다.

Spring 재동기화용 Python 내부 조회는
`GET /internal/projects/{projectId}/graph-snapshot`이다. 전체 Event v1과
Category cascade/Soft Delete 계약은 `docs/contracts/python-event-contract-v1.md`,
`docs/contracts/graph-category-and-soft-delete.md`를 따른다.
`GET /health/ready`도 실제 DB의 Alembic revision이 이 head와 다르면 503을 반환한다.

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

`DATABASE_URL_TEST`가 PostgreSQL URL이면 테스트마다 별도의 폐기 가능한 데이터베이스를 만들고
Alembic head를 적용한 뒤 삭제한다. 원본 URL의 데이터베이스는 관리자 연결에만 사용하며 테스트
데이터를 쓰지 않는다. migration downgrade/upgrade 왕복 테스트의 `TEST_POSTGRESQL_URL`에는
반드시 별도로 만든 폐기 가능한 DB만 지정한다. 일반 개발 DB인 `pipeline`을
`TEST_POSTGRESQL_URL`로 지정하지 않는다.

기존 ACTIVE/UNATTACHED Node의 current Revision을 기준으로 Retrieval
Embedding을 점검·재생성하는 운영 절차는
[`docs/operations/node-embedding-backfill.md`](docs/operations/node-embedding-backfill.md)를
따른다. 도구는 기본 dry-run이며 실제 반영에는 `--apply`가 필요하다.

## 제한된 실제 GMS Fatal-Safety Smoke

이 검사는 S3·SQS·Clova만 건너뛰고, 합성 Transcript 이후의 운영
`run_automatic_meeting()` 경로를 그대로 실행한다. Candidate LLM 2단계,
Candidate별 Embedding, Node별 B-model, Retrieval, Graph 원자 적용, Outbox,
Fake Meeting Summary 완료 장벽을 테스트 전용 PostgreSQL에서 확인한다. batch나
사전 생성 결과 replay로 운영 판단을 대체하지 않는다.

기본 테스트에서는 실제 Provider가 계속 차단된다. 아래 전용 명령에서만 두 안전
플래그와 하드 예산을 함께 사용한다. `.env`의 credential 값은 출력하거나 산출물에
기록하지 않는다.

```powershell
$env:NO_EXTERNAL_AI_CALLS = "1"
$env:ALLOW_GMS_FATAL_SMOKE = "1"

.\.venv\Scripts\python.exe tests\tools\smoke\gms_fatal_smoke.py `
  --env-file .env `
  --max-candidate-calls 2 `
  --max-b-model-calls 4 `
  --max-embedding-items 9 `
  --max-http-requests 15 `
  --no-provider-retry `
  --cleanup-db
```

결과는 `outputs/gms-fatal-smoke/<RUN_ID>/`와 같은 이름의 ZIP에 기록된다.
격리 DB 이름은 항상 `gms_smoke_*`이며 성공·실패 모두 종료 시 삭제한다. 기존
`pipeline` DB에는 테스트 데이터를 쓰지 않는다.

## 디렉터리
```
data-pipeline/
├── data_pipeline/
│   ├── api/            # FastAPI Graph 조회·사용자 직접 편집 내부 경계
│   ├── analysis_worker/# 레거시 승인 흐름용 비동기 분석 호환 Worker
│   ├── outbox_publisher/# Spring 통지 relay
│   ├── meeting_analysis/# Command·Recording join 및 병렬 task coordinator
│   ├── meeting_summary/# 회의록 port·GMS adapter·저장 service
│   ├── worker/         # S3/SQS 음성 입력 Worker
│   ├── stt/            # Fake/Clova Transcriber
│   ├── b_model/        # B 모델 port와 GMS adapter
│   ├── retrieval/      # Embedding adapter와 pgvector 검색
│   ├── contracts/      # Pydantic DTO와 상태 계약
│   ├── pipeline/       # 자동 Graph Plan·Revision·병합 및 레거시 use case
│   ├── storage/        # SQLAlchemy 모델 + Alembic 정본 PostgreSQL
│   └── normalization/  # STT 기술용어 사전·규칙·service
├── docs/
│   ├── contracts/      # API·Outbox·SQS/OpenVidu 데이터 계약
│   ├── operations/     # FastAPI·Worker·B 모델·AWS 실행
│   ├── handoffs/       # Spring 등 다른 담당자 인수인계
│   └── reports/        # 시점이 고정된 E2E·품질 결과
├── outputs/            # E2E 결과(Git 제외)
├── scripts/            # 운영 backfill 등 제품 유지보수 CLI
├── tests/
│   ├── config/         # 외부 호출 차단 Fake 환경
│   ├── fixtures/       # STT·계약·평가 gold 입력
│   ├── evaluation_support/ # 제품 패키지와 분리된 평가 지원 코드
│   ├── tools/          # evaluation·integration·smoke 수동 검증 CLI
│   ├── evaluation/     # 평가 코드 회귀 테스트
│   └── operations/     # 운영 도구 안전성 테스트
├── alembic.ini, docker-compose.yml, .env.example, .gitlab-ci.yml
```

## 검증 9규칙 (validation/ + pipeline/)
| # | 규칙 | 위치 |
| --- | --- | --- |
| 1 | itemId 유일성 (중복 → 응답 무효, 전부 MINUTES_ONLY) | `validation/judgments.py` |
| 2 | 후보 allowlist (기존 노드 참조는 후보 목록에만) | `validation/judgments.py` |
| 3 | 부모 유효성 (Decision root / Action→Decision / Issue→Decision·Action) | `contracts/enums.py`, `validation/judgments.py` |
| 4 | evidence (segmentId 실존 + 부분 문자열 + 최소 10자 + 오프셋 역산) | `validation/evidence.py` |
| 5 | Category Graph partition — 교차 Category MERGE·부모 LINK 차단 | `contracts/enums.py`, `retrieval/search.py` |
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
- **프롬프트**: `data_pipeline/prompts/`(정본 템플릿+sha), 과거 PoC↔M2 규칙 대응은 `docs/reference/legacy-prompts/RULE_MAP.md`.
  granularity 규칙은 이식하지 않음(폐기 실험). R8 은 §T-1 대기 중이라 현행 유지.
- **체인**: `data_pipeline/pipeline/chain.py` — 세그먼트 → ① → itemId 유일성/evidence 검증 → ②(후보 없음)
  → 모든 item을 `NodeCandidate`로 PG에 저장한다. 사용자 승인 전에는 정식 Node/Relation/NodeEvidence를
  만들지 않는다. ①/② 프롬프트·raw·sha·토큰·lineage는 선택적으로 `outputs/<run>/<meeting>/`에 저장한다.
- **LLM 어댑터**: `data_pipeline/llm/` (GMS OpenAI 호환, gpt-5.2, json_object, timeout 180s, retry 2).
  키는 `.env`(GMS_KEY)로만. 오프라인 테스트는 FakeClient — openai 미설치여도 green.
- **회귀**: `tests/tools/evaluation/run_m2_regression.py` (gold 5회의). gold 어댑터가 회의 간 판정(ATTACH D-*/A-*, UPDATE_ACTION)을
  **UNATTACHED 기대값으로 변환**한다(gold 원본 무수정, `tests/fixtures/evaluation/gold_adapter.py`). 회귀 결과는
  Git에 커밋하지 않는 `outputs/`에 기록한다.
- **실행**:
  ```bash
  # 오프라인 (LLM 없이) — 체인/어댑터 로직 검증
  pytest
  # 실 LLM 회귀 (크레딧 소비, .env 의 GMS_KEY 필요)
  python tests/tools/evaluation/run_m2_regression.py --meetings M2X,M2Y,M1,M2,M3 --max-credits 8000 \
    --env-file /path/to/.env
  ```

## 설계 문서(kickoff v2.1 + v2.2) 대조 상태
설계 문서를 확보해 M1 스코프 항목을 전부 대조 반영했다.
- **일치**: D1′ 상태 모델 분리, §3 부모 규칙, §2 UNIQUE 키, D1‴ parent_id 단일 진실,
  D2′ Plan 원자 적용, M4 관계 모델(SAME/REVERSES/FOLLOWS/RESOLVED_BY × PROPOSED/CONFIRMED/REJECTED),
  §5 단순화(command 테이블 없음·advisory lock 없음·범용 outbox·임베딩 계약 버전 고정), 검색 설정값 분리.
  임베딩 계약은 현재 `v2-no-category`다. Category는 Embedding 의미에서 제외되어
  Category만 바꾸는 수정은 벡터를 STALE로 만들지 않고 제공자 호출도 발생시키지
  않는다. Category는 메타데이터·화면·MERGE 검색 범위·B 모델 입력에서는 그대로
  쓰인다. 자세한 내용은 [docs/operations/node-embedding-backfill.md](docs/operations/node-embedding-backfill.md).
- **문서에 맞춰 정정**: R4′ node_embedding PK(node_id, embedding_version)+embedded_text_hash/status,
  D1″ transcript_segment(sequence_no·text_hash) / node_evidence(quote_start·quote_end·evidence_type·source_meeting_id),
  §5 outbox 타입(EMBEDDING_REQUESTED / MEETING_PROCESSING_COMPLETED / GRAPH_CHANGED),
  M4 재제안 억제 키 컬럼(from/to_content_hash·merge_rule_version, 로직은 병합 코드와 함께 후속).
- **§T 미확정으로 보류**: 카테고리 최종 enum(§T-2) — 리뷰어 권장안은 `DATA` 포함(PLANNING/DESIGN/
  FRONTEND/BACKEND/AI/INFRA/**DATA**/ETC)이나 현재 config 기본값은 작업 지시 임시값 7종. 확정 시
  `categories.json` + 재시딩 1개로 반영(§T-2 승인 대기). follows 자동화·R8 등 나머지 §T 블로커는 M2+.
