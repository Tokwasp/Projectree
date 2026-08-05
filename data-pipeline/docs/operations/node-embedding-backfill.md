# Node Embedding Backfill 운영 가이드

## 1. 목적

기존 Graph Node가 현재 Retrieval 설정과 일치하는 `READY` Embedding을 갖도록
점검하고, 필요한 경우 제한적으로 재생성한다. Embedding이 없는 Node는 검색
후보에서 제외되므로 자동 MERGE 평가 전에 이 작업이 필요하다.

이 도구는 `node_embedding`만 변경한다. Node 상태·version·Revision·Evidence·
Relation·Merge·Analysis Run·Outbox는 변경하지 않는다.

## 2. 대상 Node

`--project-id`는 필수다. 기본 대상은 같은 프로젝트에서 아래 조건을 만족하는
Node다.

```text
graph_state IN (ACTIVE, UNATTACHED)
merged_into_node_id IS NULL
```

`MERGED`, `EXCLUDED`, `ARCHIVED`, `DELETED`, 다른 프로젝트 Node는 제외한다.
`--node-id`를 사용해도 project 범위를 넘을 수 없다. `current_revision_id`가
없거나 관계가 손상된 Node는 provider를 호출하지 않고
`NO_CURRENT_REVISION` 또는 `INVALID_CURRENT_REVISION`으로 보고한다.

## 3. current Revision 정본 계약

Embedding 의미의 정본은 다음 경로다.

```text
Node.current_revision_id
→ NodeRevision
→ NodeRevisionEvidence
→ Evidence
```

Node projection 컬럼과 current Revision이 다르면 current Revision의
`node_type`, `title`, `content`를 사용한다. `category`는 v2 계약에서
Embedding 의미에 포함되지 않는다(§아래 4절). Evidence는 내부 `start_ms`,
`source_segment_id`, `quoted_text` 순으로 정렬한 뒤 canonical text에는
`(source_segment_id 또는 "", quoted_text)`만 넣는다. `requires_evidence=false`인
LEGACY Revision은 Evidence가 없어도 허용한다. 확인할 수 없는 Evidence를
새로 만들지는 않는다.

## 4. canonical text/hash

자동 Graph, Analysis 재Embedding, backfill은 같은 serializer를 사용한다.
계약 버전은 `v2-no-category`이며 `category`를 **포함하지 않는다**.

```json
[
  "ACTION",
  "제목",
  "내용",
  [["segment-1", "근거 문장"]]
]
```

`category`가 빠진 이유는 Category가 분류 메타데이터이지 의미가 아니기
때문이다. 이 덕분에 Category만 바꾸는 Revision은 `embedded_text_hash`를
바꾸지 않고, 따라서 벡터가 STALE이 되지 않으며 제공자 호출도 발생하지
않는다. Category는 Node/NodeRevision 메타데이터, 화면, MERGE 검색 범위,
통계, B 모델 입력에서는 그대로 쓰인다.

v1(`category` 포함)과 v2 벡터는 절대 같은 후보 집합에 섞이지 않는다.
검색이 `embedding_version`으로 필터링하므로, 버전을 바꾸면 backfill 전까지
해당 Node는 후보에서 제외된다.

Evidence를 `start_ms`(없는 값은 마지막)→segment ID→quote 순으로 정렬한 뒤
시간 숫자를 제외하고 `ensure_ascii=False`,
`separators=(",", ":")`로 JSON을 만들고 UTF-8 SHA-256을 계산한다.
`due_date`, 부모, graph state, version은 입력에 넣지 않는다. Node 진행 상태
도메인은 제품에서 제거됐다.

## 5. 재사용과 재생성 판정

현재 설정의 model/version/dimension/hash와 일치하고, 상태가 `READY`이며,
저장 vector가 유한한 비영(非零) 정규 dimension이면 `READY_REUSABLE`로
건너뛴다. 누락·`STALE`·`FAILED`·`PENDING`·vector 누락·model/dimension/hash
불일치·vector 검증 실패는 재생성 대상이다.

`READY`지만 잘못된 row는 apply에서 provider 호출 전에 짧은 트랜잭션으로
`STALE` 처리한다. provider가 실패해도 잘못된 vector가 검색에 계속 사용되지
않는다.

## 6. Dry-run

기본 실행은 외부 호출과 DB mutation이 없는 dry-run이다.

```powershell
.\.venv\Scripts\python.exe scripts\operations\backfill_node_embeddings.py `
  --project-id "<project-id>"
```

먼저 `wouldGenerate`, `reusable`, skip reason, 예상 호출량과 마지막 cursor를
확인한다. dry-run에서는 embedding client 자체를 만들지 않는다.

## 7. 제한 적용

실제 적용은 승인된 환경에서 `--apply`와 작은 호출 상한을 함께 명시한다.

```powershell
.\.venv\Scripts\python.exe scripts\operations\backfill_node_embeddings.py `
  --project-id "<project-id>" `
  --max-calls 10 `
  --sleep-seconds 0.5 `
  --apply
```

Node는 UUID 오름차순으로 처리되고 각각 독립 transaction을 사용한다.
provider HTTP 호출 중에는 DB transaction이나 row lock을 유지하지 않는다.
한 Node 실패 후에도 다음 Node를 처리하며, 실패가 하나라도 있으면 CLI는
non-zero로 종료한다.

## 8. 재개

리포트의 `lastScannedNodeId`를 확인하고 다음처럼 재개한다.

```powershell
.\.venv\Scripts\python.exe scripts\operations\backfill_node_embeddings.py `
  --project-id "<project-id>" `
  --after-node-id "<last-scanned-node-id>" `
  --max-calls 10 `
  --apply
```

`--batch-size`는 DB pagination 크기이고 provider batch 호출 크기가 아니다.
`--node-id`와 `--limit`으로 더 작은 범위를 점검할 수 있다.
기존 `scripts/backfill_node_embeddings.py`는 같은 `main()`을 호출하는 호환
wrapper로 유지한다.

## 9. 리포트

기본 경로는 아래와 같다.

```text
outputs/embedding-backfill/<RUN_ID>/report.json
outputs/embedding-backfill/<RUN_ID>/summary.md
```

리포트는 count, reason, Node ID, 이전 상태, hash prefix, latency만 기록한다.
DB URL, secret, 제목·본문·Evidence, 전체 입력/hash/vector, provider 원문
응답은 기록하지 않는다.

## 10. 실패 처리

- `NODE_CHANGED_DURING_EMBED`: 호출 중 Node version/current Revision/hash가
  바뀌어 결과를 폐기했다. 다음 실행에서 재처리한다.
- `CONCURRENT_READY_REUSED`: 다른 실행이 올바른 READY row를 먼저 저장해
  기존 값을 재사용했다.
- `EMBEDDING_PROVIDER_FAILED` / `EMBEDDING_INVALID`: 새 vector를 저장하지
  않는다.
- `DB_WRITE_FAILED`: 해당 Node transaction을 rollback하고 다음 Node로 간다.
- `DEFERRED_MAX_CALLS`: 호출 상한 때문에 다음 실행으로 미뤘다.

무제한 자동 재시도는 하지 않는다.

## 11. 보안 주의사항

- `.env`, `GMS_KEY`, `DATABASE_URL`을 출력하거나 리포트에 저장하지 않는다.
- 실제 text, Evidence, vector, provider 응답을 로그로 남기지 않는다.
- 운영/개발 DB에 임의로 `--apply`하지 않는다.
- Alembic upgrade/stamp, DB drop/truncate를 이 도구와 함께 실행하지 않는다.

## 12. 실제 적용 전 체크리스트

1. 대상 project ID와 DB 환경을 재확인한다.
2. 현재 Alembic head가 애플리케이션과 일치하는지 별도로 확인한다.
3. `RETRIEVAL_EMBEDDING_MODEL`, `VERSION`, `DIM`을 확인한다.
4. dry-run 리포트와 예상 호출량을 검토한다.
5. `EMBEDDING_ADAPTER=gms|openai`, base URL, key, timeout을 확인한다.
6. `--max-calls`를 작게 둔 제한 실행부터 시작한다.
7. 실패·stale·변경 중 폐기 건을 확인한 뒤 cursor로 재개한다.

## 13. 평가 전 완료 조건

- 평가 프로젝트의 ACTIVE/UNATTACHED canonical Node가 valid READY이거나
  명확한 skip reason을 가진다.
- `failed`, `deferred`, 손상 Revision을 검토했다.
- 같은 명령 재실행 시 대상이 `READY_REUSABLE`로 멱등 종료된다.
- 실제 Retrieval에서 설정과 일치하는 READY row만 조회되는지 확인한다.
