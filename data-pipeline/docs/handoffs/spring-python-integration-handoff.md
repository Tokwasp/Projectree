# Spring ↔ Python 연동 인수인계

**대상**: Spring 담당자
**Python 측 상태**: 검토 API·비동기 분석·Outbox 구현 완료. **Spring 코드는 수정하지 않았다.**

관련 문서
- [`python-review-api-contract.md`](../contracts/python-review-api-contract.md) — REST 계약
- [`python-outbox-event-contract.md`](../contracts/python-outbox-event-contract.md) — 이벤트 계약
- [`python-server-runtime.md`](../operations/python-server-runtime.md) — 실행/배포
- [`sqs-message-contract-comparison.md`](../contracts/sqs-message-contract-comparison.md) — 음성 수집 계약

---

## 1. 전체 그림

```text
[자동]  OpenVidu → SQS → Python Worker → S3 → Clova → LLM
          → PostgreSQL(Candidate, INITIAL_REVIEW_PENDING) → Worker 종료

[검토]  Frontend → Spring → Python FastAPI → PostgreSQL

[1차 검토 완료]
        Spring → POST /initial-review/complete → 202 Accepted
          → UNATTACHED Node 생성 + analysis_job 등록 + outbox event
          → Analysis Worker(별도 프로세스) → 임베딩 → pgvector → B 모델
          → FINAL_REVIEW_PENDING

[최종]  Spring → POST /analysis-candidates/{id}/approve-* → 그래프 반영

[통지]  도메인 변경과 같은 트랜잭션의 outbox_event → Outbox Publisher → Spring
```

**사용자 승인을 기다리며 Python 프로세스나 SQS 메시지를 점유하지 않는다.**

---

## 2. 식별자 — 가장 중요한 미해결 사항

### 2-1. `Project.id` 타입 불일치 (차단)

| 시스템 | 타입 | 근거 |
|---|---|---|
| Spring | `int` auto-increment | `Backend/.../project/entity/Project.java:16-18` |
| Python | `String(128)` (실제로 UUID 문자열 사용 중) | `storage/models.py` `project_id` |

Python은 문자열이라 **둘 다 저장은 되지만**, 두 시스템이 같은 프로젝트를 같은 값으로
부르지 않으면 데이터가 갈라진다.

**결정 필요**: `projectId`의 정본을 무엇으로 할 것인가?
- (a) Spring `int`를 문자열로 그대로 전달 → Python은 `"42"` 저장
- (b) Spring에 프로젝트 UUID 컬럼 추가
- (c) 매핑 테이블

Python API는 `X-Project-Id` 헤더 값을 그대로 쓰므로, 어느 쪽이든 **Spring이 일관되게
같은 값을 보내기만 하면** 된다.

Spring은 가능하면 사용자 요청의 추적 ID를 `X-Request-Id`로 전달한다. Python은
응답에도 같은 헤더를 반환한다. 전체 요청 body는 기본 1 MiB, 제목 300자, 본문
20,000자, 초기 검토 Candidate는 1회 최대 200개다.

### 2-2. `roomName` → `projectId` 매핑 (차단)

OpenVidu egress 메시지에는 **`projectId`가 없다.** `roomName`뿐이다.
조사 결과 Spring에는 meeting/room 개념 자체가 없다 (`meeting`, `room`, `openvidu`,
`egress`, `roomName`, `UUID` 문자열이 Backend 전체에서 **0건**).

Python 쪽에는 이미 포트가 준비되어 있다.
```python
class MeetingContextResolver(Protocol):
    def resolve_by_openvidu_room(self, room_name: str) -> MeetingContext | None: ...
```
기본 구현은 **항상 실패**한다 (`UnavailableMeetingContextResolver`). 추측으로 매핑을
만들지 않았다 — 잘못된 프로젝트에 회의가 기록되는 것보다 소리내어 실패하는 편이 낫다.

**Spring이 제공해야 할 것 (택 1)**
1. room 생성 시점에 `roomName ↔ projectId ↔ meetingId`를 저장하는 테이블 + 조회 API
2. 공유 테이블
3. producer가 `roomName`이나 `objectKey`에 `projectId`를 포함 (가장 저렴, 녹화 서비스 변경 필요)

상세:
[`sqs-message-contract-comparison.md`](../contracts/sqs-message-contract-comparison.md) §6.

---

## 3. Python API 인증 — 미확정

**현재 인증이 없다.** `X-Project-Id` 헤더를 그대로 신뢰한다.

→ **Python API를 내부망에 두고 Spring만 접근 가능하게 해야 한다.**

결정 필요:
- 서비스 간 인증 방식 (mTLS / 공유 시크릿 헤더 / 네트워크 격리만)
- Spring이 사용자 세션에서 `projectId`를 검증한 뒤 전달하는 구조가 맞는지

Python 측 적용 지점은 `data_pipeline/api/dependencies.py::get_project_id` **한 곳**이다.

---

## 4. 검토 화면 API 목록

| 화면 | Method | Path |
|---|---|---|
| 진행 상태 | GET | `/api/v1/meetings/{meetingId}/pipeline-status` |
| 1차 검토 목록 | GET | `/api/v1/meetings/{meetingId}/candidates` |
| 후보 상세 | GET | `/api/v1/candidates/{candidateId}` |
| 후보 수정 | PATCH | `/api/v1/candidates/{candidateId}` |
| 후보 승인 | POST | `/api/v1/candidates/{candidateId}/approve` |
| 후보 거절 | POST | `/api/v1/candidates/{candidateId}/reject` |
| **1차 검토 완료** | POST | `/api/v1/meetings/{meetingId}/initial-review/complete` → **202** |
| 분석 진행 상태 | GET | `/api/v1/meetings/{meetingId}/analysis-status` |
| 최종 검토 목록 | GET | `/api/v1/meetings/{meetingId}/final-review` |
| 재분석 | POST | `/api/v1/nodes/{nodeId}/reanalyze` → **202** |
| 최종 승인 (신규) | POST | `/api/v1/analysis-candidates/{id}/approve-create` |
| 최종 승인 (연결) | POST | `/api/v1/analysis-candidates/{id}/approve-link` |
| 최종 승인 (병합) | POST | `/api/v1/analysis-candidates/{id}/approve-merge` |
| 최종 거절 | POST | `/api/v1/analysis-candidates/{id}/reject` |
| liveness | GET | `/health/live` |
| readiness | GET | `/health/ready` |

전체 스펙: `GET /openapi.json`

---

## 5. 상태 흐름

```text
Candidate.review_status : PENDING → APPROVED | REJECTED
Node.graph_state        : UNATTACHED → ACTIVE | MERGED
analysis_job.status     : PENDING → RUNNING → SUCCEEDED | FAILED
AnalysisCandidate.status: PENDING → APPROVED | REJECTED
outbox_event.status     : PENDING → PUBLISHING → PUBLISHED | DEAD
```

화면 단계 매핑 (`pipeline-status.pipelineStage`)

```text
INITIAL_REVIEW_PENDING  →  1차 검토 화면
ANALYZING               →  분석 중 (스피너)
FINAL_REVIEW_PENDING    →  최종 검토 화면
FAILED                  →  실패 안내
REVIEW_COMPLETED        →  완료
```

---

## 6. Outbox 이벤트 수신 — 결정 필요

| 항목 | 상태 |
|---|---|
| 수신 방식 | **미확정**. HTTP callback 또는 SQS |
| Python 측 준비 | transport port 분리 완료. `FakeOutboxTransport`, `HttpCallbackTransport` 제공 |
| SQS transport | 미구현 (수신 방식 확정 후 추가) |

### eventId 중복 처리 (Spring 필수 작업)

전달은 **at-least-once**다. 같은 `eventId`가 두 번 이상 올 수 있다.

```text
Spring 은 수신한 eventId 를 저장하고, 이미 처리한 eventId 는 무시해야 한다.
```

권장: `processed_event(event_id PK, processed_at)`에 INSERT하고 unique 위반이면 skip.
처리와 기록은 **같은 트랜잭션**이어야 한다.

**Exactly-once가 아니다.** 그렇게 가정한 설계를 하지 말 것.

### timeout / retry

- Python은 2xx가 아니면 실패로 보고 지수 backoff(2초 → 최대 3600초)로 재시도한다.
- 기본 `max_attempts` = 8. 초과하면 `DEAD`로 격리된다.
- 따라서 Spring endpoint는 **멱등**이어야 하고, 응답이 느리면 중복 수신이 늘어난다.
- 허용 응답 시간 합의 필요 (기본 timeout 10초).

### 실패 UI

`PIPELINE_FAILED` 이벤트 payload:
```json
{"meetingId":"...","nodeId":"...","stage":"ANALYSIS","failureCode":"EmbeddingTransportError"}
```
사용자에게 무엇을 보여줄지, 재시도 버튼을 제공할지(→ `POST /nodes/{id}/reanalyze`) 결정 필요.

---

## 7. ACTION 상태 전달 (Spring 화면 반영 필요)

기존에는 모든 ACTION Node가 `TODO`로 생성됐다. 이제 회의 발언의 시제가 Node까지 전달된다.

```text
"하겠습니다"          → TODO
"진행 중입니다"       → IN_PROGRESS
"했습니다/확인했습니다" → COMPLETED
"취소했습니다"        → CANCELLED
```

`CandidateView`의 새 필드:

| 필드 | 화면에서의 용도 |
|---|---|
| `suggested_lifecycle_status` | LLM 제안 (없으면 `null`) |
| `reviewed_lifecycle_status` | 검토자 override |
| `effective_lifecycle_status` | **Node에 실제 들어갈 값** — 이걸 표시 |
| `lifecycle_status_needs_review` | `true`면 "상태 확인 필요" 배지 권장 |

수정: `PATCH /api/v1/candidates/{id}` body에 `lifecycleStatus`.
**ACTION에만 허용**되며 DECISION/ISSUE에 지정하면 422.

> 현재 동결된 LTS 프롬프트는 `lifecycleStatus`를 **아직 내지 않는다**(AGENTS.md가 프롬프트
> 변경을 금지). 따라서 당분간 `suggested_lifecycle_status`는 `null`이고
> `lifecycle_status_needs_review`가 `true`이며, 검토자가 화면에서 지정하는 흐름이 된다.
> 저장·전달 경로는 이미 완성되어 있으므로, 새 프롬프트 프로파일이 값을 채우면 즉시 동작한다.

---

## 8. Spring 담당자 체크리스트

```text
[ ] projectId 타입 정본 결정 (int vs UUID)
[ ] roomName → projectId/meetingId 매핑 데이터 소스 제공
[ ] Python API 인증 방식 결정 (현재 무인증, 내부망 전용)
[ ] Python API 내부망 배치 및 방화벽 설정
[ ] Outbox 수신 방식 결정 (HTTP callback vs SQS)
[ ] HTTP라면 endpoint URL + 인증 헤더 제공
[ ] eventId 중복 제거 테이블 구현
[ ] Outbox endpoint 멱등성 보장
[ ] PIPELINE_FAILED 수신 시 실패 UI 정의
[ ] 검토 화면에 effective_lifecycle_status / lifecycle_status_needs_review 반영
[ ] 최종 승인 시 expectedVersion 전달 (409 처리 포함)
[ ] ACTION/ISSUE를 ACTIVE로 만들려면 confirmed parent 필요함을 UI에 반영
[ ] meetings/* S3 IAM 권한 부여 (음성 수집 차단 요소)
[ ] SQS DLQ 설정
```

---

## 8-1. 최종 검토 화면 추가 요구사항 (2026-08-01 라이브 E2E 반영)

실제 GMS B 모델로 전체 검토 흐름을 검증하면서 확인된 UI 요구사항이다.

1. **부모 없는 ACTION/ISSUE의 CREATE_NEW/RELATED_TO 승인은 항상 409다**
   (제품 규칙: ACTION/ISSUE는 confirmed parent 없이 ACTIVE 불가).
   → 최종 검토 화면은 이런 후보에 "미연결 유지(reject)" 종결 버튼을 제공해야 한다.
   reject 후 노드는 UNATTACHED로 보존된다.
2. **409 "Candidate target is no longer valid" 수신 시** — 같은 회의의 다른 승인(MERGE 등)이
   target을 변경한 경우다. `POST /api/v1/nodes/{nodeId}/reanalyze` → 분석 완료 대기 →
   final-review 재조회 흐름을 UI에 넣어라.
3. **승인 순서 안내**: 같은 회의에서 DECISION(부모 후보)을 먼저 최종 승인하면
   ACTION/ISSUE 자식의 LINK(ATTACHED_TO) 승인이 가능해진다.
4. final-review 목록은 이제 **현재 분석 run의 후보만** 반환한다(재분석 후 옛 후보 자동 제외).
5. `candidate-quality-v1` 프로필 활성화 시 후보 목록의 `suggested_lifecycle_status`가
   실제 값(TODO/IN_PROGRESS/COMPLETED/CANCELLED)으로 채워진다 — 검토 화면에 표시할 것.
6. 1차 검토 화면: `request.warnings`의 `DEMOTED:<itemId>:<rule>` 항목을 노출하면
   "왜 이 항목이 회의록 전용으로 내려갔는지"를 사용자가 알 수 있다.

## 9. Python이 하지 않은 것

- **Spring 코드 수정 없음.** 한 줄도 건드리지 않았다.
- AWS 리소스 변경 없음 (IAM, DLQ, 큐 모두 문서화만).
- 인증 구현 없음.
- B 모델·Embedding GMS/OpenAI 호환 adapter는 구현됨. 실제 실행 credential과
  프로세스 배포는 인프라 설정이 필요함.
- 동결된 LTS 프롬프트 변경 없음.
