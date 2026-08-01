# Python 검토 API 계약 (v1)

**Base URL**: `http://<python-host>:8000`
**OpenAPI**: `GET /openapi.json`, Swagger UI `GET /docs`
**Contract version**: `1.0.0`

---

## 0. 공통 규약

### 인증 — 미구현 (중요)

**현재 인증이 없다.** 모든 요청은 신뢰되며, 프로젝트 범위는 헤더로만 결정된다.

| 헤더 | 필수 | 설명 |
|---|:---:|---|
| `X-Project-Id` | ✅ | 프로젝트 범위. 누락 시 **422** |
| `X-Actor-Id` | — | 감사 로그용 행위자. 기본값 `api` |
| `X-Request-Id` | — | 요청 추적 ID. 안전한 128자 이하 값이면 응답에 그대로 반환 |

→ **내부망에서 Spring만 접근 가능하도록 배치해야 한다.**
인증이 도입되면 `data_pipeline/api/dependencies.py::get_project_id` 한 곳만 바꾸면 된다.
`X-Project-Id`는 그때 검증된 주체에서 파생되어야 하며, 호출자가 임의로 지정할 수 없어야 한다.

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
| initial-review/complete | 이미 처리된 후보는 건너뛰고, job이 없는 Node만 큐잉 |
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

`CandidateView`의 lifecycle 관련 필드:

| 필드 | 설명 |
|---|---|
| `suggested_lifecycle_status` | LLM이 시제에서 추론한 ACTION 상태. 없으면 `null` |
| `reviewed_lifecycle_status` | 검토자 override |
| `effective_lifecycle_status` | **Node에 실제로 들어갈 값** |
| `lifecycle_status_needs_review` | ACTION인데 제안이 없어 기본값으로 폴백된 경우 `true` |

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
  "lifecycleStatus": "COMPLETED",
  "parentMode": "NONE"
}
```

- `lifecycleStatus`: `TODO`/`IN_PROGRESS`/`COMPLETED`/`CANCELLED`. **ACTION에만 허용** — DECISION/ISSUE에 지정하면 **422**. `null`을 명시하면 override 해제.
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

| Endpoint | Body |
|---|---|
| `POST /api/v1/analysis-candidates/{id}/approve-create` | `{"expectedVersion": 1}` |
| `POST /api/v1/analysis-candidates/{id}/approve-link` | `{"expectedVersion": 1}` |
| `POST /api/v1/analysis-candidates/{id}/approve-merge` | `{"expectedVersion":1, "confirmUnattachedTarget":false, "mergedTitle":null, "mergedContent":null}` |
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
- MERGE 대상이 `UNATTACHED`면 `confirmUnattachedTarget: true`가 필요하다. 아니면 **409**.
- ACTION/ISSUE를 ACTIVE로 만들려면 **confirmed parent**가 필요하다 (`ATTACHED_TO` + `CONFIRMED`). 없으면 409.
- 승인은 source(및 MERGE의 target) `version`을 올린다. 이후 요청은 새 버전을 써야 한다.

---

## 5. 예시

```bash
# 1차 검토 목록
curl -H "X-Project-Id: proj-1" \
  http://localhost:8000/api/v1/meetings/meet-1/candidates

# ACTION 상태 수정
curl -X PATCH -H "X-Project-Id: proj-1" -H "X-Actor-Id: reviewer-1" \
  -H "Content-Type: application/json" \
  -d '{"expectedVersion":1,"lifecycleStatus":"COMPLETED"}' \
  http://localhost:8000/api/v1/candidates/<id>

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
