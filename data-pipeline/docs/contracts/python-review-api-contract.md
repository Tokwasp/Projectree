# Python 내부 Graph·레거시 검토 API 계약

**Base URL**: `http://<python-host>:8000`
**OpenAPI**: `GET /openapi.json`, Swagger UI `GET /docs`
**Contract version**: `2.0.0`

> Candidate 검토·재분석·승인 API는 레거시 호환 경로다. 현재 제품 경로는
> [`automatic-node-merge.md`](automatic-node-merge.md)와
> Graph API이며 운영/스테이징에서는 레거시 router가 기본 비활성이다.

---

## 0. 공통 규약

### 내부 서비스 인증과 프로젝트 범위

운영/스테이징은 `INTERNAL_API_TOKEN`과 동일한
`X-Internal-Service-Token`을 요구한다. 모든 데이터 요청은 별도로
`X-Project-Id` 범위를 검증한다.

| 헤더 | 필수 | 설명 |
|---|:---:|---|
| `X-Project-Id` | ✅ | 프로젝트 범위. 누락 시 **422** |
| `X-Internal-Service-Token` | 운영/스테이징 ✅ | Spring/Worker service token |
| `X-Actor-Id` | — | 감사 로그용 행위자. 기본값 `api` |
| `X-Request-Id` | — | 요청 추적 ID. 안전한 128자 이하 값이면 응답에 그대로 반환 |

→ 토큰과 별개로 **내부망에서 Spring만 접근 가능하도록 배치해야 한다.**
Spring은 사용자 권한을 확인하고 Python은 호출 서비스와 project 데이터 경계를
검증한다. 향후 `X-Project-Id`는 Spring의 검증된 주체에서 파생해야 한다.

### 상태 코드

| 코드 | 의미 |
|---|---|
| 200 | 성공 |
| 202 | 접수됨. 분석은 비동기로 진행 |
| 404 | 대상 없음 (프로젝트가 다르면 존재해도 404) |
| 409 | 버전 충돌 또는 잘못된 상태 |
| 413 | 요청 본문이 서버 제한을 초과 |
| 422 | 요청 검증 실패 |
| 500 / 502 | 내부 오류 / 외부 provider 오류 |
| 503 | readiness 실패 |

### 오류 본문

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "...",
    "expectedVersion": 1,
    "actualVersion": 2
  }
}
```

`expectedVersion` / `actualVersion`은 버전 충돌에서만 포함된다.
모든 응답에는 `X-Request-Id` 헤더가 포함된다. 예상하지 못한 500 오류와 요청 크기
오류 본문에는 같은 값의 `requestId`도 포함된다.

### 요청 제한

- 전체 body: 기본 1 MiB (`API_MAX_REQUEST_BODY_BYTES`)
- 제목: 300자
- 본문: 20,000자
- `initial-review/complete`의 `candidateIds`: 최대 200개, 중복 불가
- 프로젝트·행위자·회의·Node/Candidate 식별자: 최대 128자

### Optimistic locking

수정 계열 요청은 `expectedVersion`을 받는다. 불일치 시 **409**.
단, **요청 값이 현재 값과 완전히 동일하면 버전이 달라도 성공**으로 처리한다(멱등 재시도 허용).

### idempotency

| 동작 | 재호출 시 |
|---|---|
| approve / reject | 이미 같은 상태면 200, 변경 없음 |
| initial-review/complete | 이미 처리된 후보는 건너뛰고, 현재 Decision-first 단계에서 job이 없는 Node만 큐잉 |
| 분석 job 등록 | Node당 1행 (UNIQUE `node_id`) |

시각은 모두 **UTC offset 포함 ISO-8601**이다.

---

## 1. Health

### `GET /health/live`
프로세스 생존만 확인한다.
```json
{"status": "ok", "checks": {"process": "ok"}}
```

### `GET /health/ready`
설정, DB 연결, 실제 DB의 Alembic revision이 코드의 head와 같은지 점검한다.
**Clova/LLM/임베딩 provider를 호출하지 않는다** (readiness는 자주 폴링되므로 외부 비용·지연을 유발하면 안 된다).

- 200 정상 / **503** 비정상
```json
{"status": "ok", "checks": {"config": "ok", "database": "ok", "schema": "ok"}}
```

---

## 2. 파이프라인 상태

### `GET /api/v1/meetings/{meetingId}/pipeline-status`

```json
{
  "meetingId": "meet-1",
  "projectId": "proj-1",
  "meetingStatus": "AI_PROCESSING",
  "requestStatus": "REVIEW_PENDING",
  "candidateCounts": {"PENDING": 24},
  "nodeCounts": {"UNATTACHED": 18},
  "analysisJobCounts": {"PENDING": 18},
  "pipelineStage": "ANALYZING"
}
```

`pipelineStage`: `INITIAL_REVIEW_PENDING` → `ANALYZING` → `FINAL_REVIEW_PENDING` / `FAILED` / `REVIEW_COMPLETED` / `UNKNOWN`

---

## 3. Candidate (1차 검토)

### `GET /api/v1/meetings/{meetingId}/candidates`

Query: `reviewStatus` (`PENDING`/`APPROVED`/`REJECTED`), `nodeType` (`DECISION`/`ACTION`/`ISSUE`/`UNKNOWN`)

```json
{"meetingId": "meet-1", "total": 24, "candidates": [ /* CandidateView */ ]}
```

### `GET /api/v1/candidates/{candidateId}`
`{"candidate": CandidateView}` / 없으면 404

### `PATCH /api/v1/candidates/{candidateId}`

**보낸 필드만 변경**된다. 생략한 필드는 건드리지 않는다.

```json
{
  "expectedVersion": 1,
  "nodeType": "ACTION",
  "category": "BACKEND",
  "title": "...",
  "content": "...",
  "disposition": "UNATTACHED",
  "parentMode": "NONE"
}
```

- 알 수 없는 필드 → 422 (`extra="forbid"`)
- 200: `{"candidates": [...], "createdNodeIds": [], "warnings": []}`

### `POST /api/v1/candidates/{candidateId}/approve`
`{"expectedVersion": 1}` (생략 가능)
승인된 Candidate를 **UNATTACHED Node 1개**로 만든다. Relation을 만들지 않고 ACTIVE로 올리지 않는다.
**분석은 시작하지 않는다** — 아래 meeting 단위 endpoint가 큐잉한다.

### `POST /api/v1/candidates/{candidateId}/reject`
`{"expectedVersion": 1}` (생략 가능). 이미 REJECTED면 200.

### `POST /api/v1/meetings/{meetingId}/initial-review/complete` → **202**

```json
{"candidateIds": []}
```
`candidateIds`가 비면 해당 회의의 **모든 PENDING** 후보를 처리한다.
최대 200개이며 중복 ID는 422로 거부한다.

```json
{
  "meetingId": "meet-1",
  "status": "ANALYSIS_PENDING",
  "reviewedCandidateCount": 24,
  "createdNodeCount": 18,
  "queuedAnalysisJobCount": 18,
  "createdNodeIds": ["..."]
}
```

**202를 반환하는 이유**: 임베딩·Retrieval·B 모델을 요청 안에서 실행하지 않는다.
`analysis_job` 행이 영속화되고 Analysis Worker가 가져간다. 프로세스가 재시작해도 유실되지 않는다.

**멱등**: 다시 호출하면 이미 job이 있는 Node는 건너뛴다 (`queuedAnalysisJobCount: 0`).

**Decision-first 큐잉**:

- Decision이 하나 이상이면 1차 검토 직후에는 Decision Job만 생성한다.
- Action/Issue Node와 Evidence는 그대로 생성하지만 Job·Run·AnalysisCandidate는
  아직 만들지 않는다.
- 모든 Decision source가 사용자 최종 결정으로 `ACTIVE` 또는 `MERGED`가 된
  트랜잭션에서 대기 중 Action/Issue Job과 `ANALYSIS_QUEUED` Outbox를 생성한다.
- Decision이 0개면 Action/Issue Job을 즉시 생성한다.
- 수동 결정으로 진행 중 Decision Job이 `FAILED`가 된 경우
  `failureCode=MANUAL_DECISION_COMPLETED`는 운영 실패가 아니라 사용자 종료
  사유이며 전체 단계의 FAILED 판정에서 제외한다.

---

## 4. 분석 및 최종 검토

### `GET /api/v1/meetings/{meetingId}/analysis-status`

```json
{
  "meetingId": "meet-1",
  "status": "ANALYZING",
  "jobs": [
    {
      "jobId": "...", "nodeId": "...", "status": "PENDING",
      "attemptCount": 0, "maxAttempts": 3,
      "failureCode": null,
      "availableAt": "2026-07-31T09:00:00+00:00",
      "updatedAt": "2026-07-31T09:00:00+00:00"
    }
  ]
}
```
`status`: `NOT_QUEUED` / `ANALYZING` / `FINAL_REVIEW_PENDING` / `FAILED`

### `GET /api/v1/meetings/{meetingId}/final-review`

`PENDING` 상태의 AnalysisCandidate 목록.

```json
{
  "meetingId": "meet-1",
  "total": 1,
  "analysisCandidates": [
    {
      "analysisCandidateId": "...", "projectId": "proj-1",
      "analysisRunId": "...", "sourceNodeId": "...", "sourceNodeVersion": 1,
      "targetNodeId": "...", "targetNodeVersion": 1,
      "recommendation": "MERGE", "relationType": null,
      "suggestedTitle": "...", "suggestedContent": "...", "reason": "...",
      "status": "PENDING", "version": 1,
      "createdAt": "2026-07-31T09:05:00+00:00"
    }
  ]
}
```

### `POST /api/v1/nodes/{nodeId}/reanalyze` → **202**
`{"expectedVersion": 1}`
```json
{"nodeId":"...", "status":"ANALYSIS_PENDING", "analysisRunId":"...", "created":true, "queuedAnalysisJobCount":1}
```

### 최종 승인

사용자의 최종 결정은 B 모델 추천과 독립적이다. 추천이 없거나
Retrieval 0건, B 모델 `SKIPPED`/`FAILED` 상태여도 다음 통합 API를
사용할 수 있다.

### `POST /api/v1/nodes/{nodeId}/decisions`

```json
{
  "requestedAction": "LINK",
  "sourceExpectedVersion": 1,
  "targetNodeId": "550e8400-e29b-41d4-a716-446655440000",
  "targetExpectedVersion": 3,
  "relationType": "RELATED_TO",
  "analysisRunId": null,
  "recommendationId": null
}
```

- `requestedAction`: `CREATE_NEW` / `LINK` / `MERGE`
- `LINK`는 target ID/version과 `relationType`이 필수다.
- `MERGE`는 target ID/version과 사용자가 확정한 `mergedTitle`,
  `mergedContent`가 필수다.
- `analysisRunId`와 `recommendationId`는 선택적인 감사 provenance다.
- `recommendationId`는 final-review가 노출하는 `analysisCandidateId`를
  의미한다. 추천과 다른 Action을 요청해도 허용되지만, source/target
  상태·version·부모 규칙은 그대로 검증한다.

기존 추천 승인 endpoint는 호환성을 위해 유지한다.

| Endpoint | Body |
|---|---|
| `POST /api/v1/analysis-candidates/{id}/approve-create` | `{"expectedVersion": 1}` |
| `POST /api/v1/analysis-candidates/{id}/approve-link` | `{"expectedVersion": 1}` |
| `POST /api/v1/analysis-candidates/{id}/approve-merge` | `{"expectedVersion":1, "mergedTitle":null, "mergedContent":null}` |
| `POST /api/v1/analysis-candidates/{id}/reject` | `{"expectedVersion": 1}` |

응답 공통:
```json
{
  "analysisCandidateId": "...", "status": "APPROVED",
  "sourceNodeId": "...", "targetNodeId": "...",
  "relationId": null, "mergeHistoryId": "..."
}
```

주의:
- MERGE 대상은 같은 project/category/type의 `ACTIVE` canonical Node만 허용한다.
- ACTION/ISSUE를 ACTIVE로 만들려면 **confirmed parent**가 필요하다 (`ATTACHED_TO` + `CONFIRMED`). 없으면 409.
- 승인은 source(및 MERGE의 target) `version`을 올린다. 이후 요청은 새 버전을 써야 한다.

---

## 5. 예시

```bash
# 1차 검토 목록
curl -H "X-Project-Id: proj-1" \
  http://localhost:8000/api/v1/meetings/meet-1/candidates

# 1차 검토 완료 → 202
curl -X POST -H "X-Project-Id: proj-1" -H "Content-Type: application/json" \
  -d '{}' \
  http://localhost:8000/api/v1/meetings/meet-1/initial-review/complete
```

---

## 6. 미확정 사항

1. **인증** — 미구현. Spring↔Python 간 인증 방식 결정 필요.
2. **pagination** — 현재 목록 endpoint에 페이징이 없다. 회의당 후보 수가 수십 개 수준이라 우선 생략했다. 필요해지면 cursor 방식을 권장한다.
3. **projectId 타입** — Spring `Project.id`는 `int`, Python `project_id`는 `String(128)`이다. 무엇을 정본으로 할지 결정 필요.
