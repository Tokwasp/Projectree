# Python Outbox 이벤트 계약

**현재 자동 Graph schemaVersion**: `auto-graph-v1`
**회의록/레거시 흐름 schemaVersion**: `v2.2`
**전달 보장**: **at-least-once** — Exactly-once가 **아니다**.

---

## 1. 왜 Outbox인가

큐를 대체하는 것이 아니다. **도메인 트랜잭션과 외부 통지의 불일치**를 막기 위한 것이다.
상태는 바뀌었는데 통지가 유실되거나, 통지는 갔는데 상태가 롤백되는 상황을 없앤다.

```text
Graph Mutation Plan 반영 + outbox_event INSERT
        ↓  (셋 다 같은 DB 트랜잭션)
      COMMIT
        ↓
  Outbox Publisher 가 별도 프로세스에서 relay
```

---

## 2. Event envelope

```json
{
  "eventId": "3f1c9a2e-0d44-4a1b-9c77-2b6e8a5d1f30",
  "eventType": "GRAPH_GENERATION_COMPLETED",
  "aggregateType": "generation_run",
  "aggregateId": "8458e748-f38e-4ead-874c-ad12f7fa3978",
  "projectId": "168a9037-485a-4145-a93f-a651fd1a254c",
  "schemaVersion": "auto-graph-v1",
  "occurredAt": "2026-07-31T09:05:00.123456+00:00",
  "payload": { }
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `eventId` | UUID | `outbox_event.id`. **중복 제거 키** |
| `eventType` | string | 현재 2종 + 레거시 호환 이벤트 |
| `aggregateType` | string | 현재 `generation_run`, 레거시 `meeting` \| `node` |
| `aggregateId` | string | 해당 aggregate 식별자 |
| `projectId` | string | 프로젝트 범위 |
| `schemaVersion` | string | `v2.2` |
| `occurredAt` | ISO-8601 (offset 포함) | 이벤트 생성 시각 |
| `payload` | object | 타입별 본문 |

**payload에는 회의 원문이나 전체 transcript를 넣지 않는다.** 식별자와 개수만 담는다.

---

## 3. Event types

### 현재 자동 Graph

| eventType | aggregateType | 발생 시점 |
|---|---|---|
| `GRAPH_GENERATION_COMPLETED` | `generation_run` | 전체 Graph Plan과 같은 트랜잭션으로 반영 완료 |
| `GRAPH_GENERATION_FAILED` | `generation_run` | 그래프를 부분 공개하지 않고 실행 실패를 영속화 |

완료 payload는 `generationRunId`, `projectId`, `externalMeetingId`, 상태,
생성·병합·관계·UNATTACHED 개수와 warnings를 포함한다. 실패 payload는 원문이나
secret 없이 `failureCode`, `errorType`만 포함한다.

### 레거시 승인 흐름

| eventType | aggregateType | 발생 시점 |
|---|---|---|
| `INITIAL_REVIEW_READY` | `meeting` | 1차 검토 완료 처리 후, 분석 큐잉과 같은 트랜잭션 |
| `ANALYSIS_QUEUED` | `node` | 분석 job 등록과 같은 트랜잭션 |
| `FINAL_REVIEW_READY` | `node` | Analysis Worker가 Retrieval·B 모델을 마친 뒤 |
| `PIPELINE_COMPLETED` | `node` | 최종 승인으로 그래프 반영 완료 (예약됨) |
| `PIPELINE_FAILED` | `node` | 분석이 재시도 한도를 넘겨 영구 실패 |

아래 5종은 이전 Candidate 승인 호출자 전환을 위해 유지한다.

### 회의록

| eventType | aggregateType | 발생 시점 |
|---|---|---|
| `MEETING_SUMMARY_READY` | `meeting_summary` | versioned 회의록 정본과 같은 트랜잭션으로 저장 완료 |

payload에는 `meetingSummaryId`, `projectId`, `externalMeetingId`,
`summaryVersion`, `status=READY`, `apiPath`만 포함하며 전체 회의록 본문이나
transcript를 넣지 않는다. 상세 계약은 `meeting-summary-contract.md`를 따른다.

### payload 예시

`INITIAL_REVIEW_READY`
```json
{"meetingId": "meet-1", "queuedNodeCount": 18}
```

`ANALYSIS_QUEUED`
```json
{"meetingId": "meet-1", "nodeId": "...", "trigger": "REANALYZE"}
```
(`trigger`는 재분석일 때만)

`FINAL_REVIEW_READY`
```json
{
  "meetingId": "meet-1",
  "nodeId": "...",
  "analysisRunId": "...",
  "analysisCandidateId": "...",
  "bModelCalled": true
}
```
`analysisCandidateId`는 Retrieval 결과가 없어 B 모델이 skip되면 `null`이다.

`PIPELINE_FAILED`
```json
{"meetingId": "meet-1", "nodeId": "...", "stage": "ANALYSIS", "failureCode": "EmbeddingTransportError"}
```

---

## 4. 전달 보장과 소비자 의무

### at-least-once

같은 `eventId`가 **두 번 이상 도착할 수 있다.** 예를 들어 transport가 성공했지만
그 결과를 기록하기 전에 Publisher가 죽으면, stall timeout 후 같은 행이 다시 발행된다.

### Spring이 해야 할 것 (필수)

```text
수신한 eventId 를 저장하고, 이미 처리한 eventId 는 무시한다.
```

권장: `processed_event(event_id PK, processed_at)` 테이블에 INSERT하고
unique 위반이면 조용히 skip. 처리와 기록은 같은 트랜잭션이어야 한다.

**Exactly-once라고 가정하지 말 것.** 이 파이프라인은 그것을 보장하지 않는다.

### 순서 보장 없음

`available_at`, `created_at` 순으로 claim하지만, 재시도 backoff 때문에
**전역 순서는 보장되지 않는다.** 순서가 필요하면 `occurredAt`으로 소비자가 정렬해야 한다.

---

## 5. Publisher 동작

```text
미발행 이벤트 batch 조회 (status PENDING, available_at <= now)
  → 행 선점 (PostgreSQL: FOR UPDATE SKIP LOCKED)
  → status = PUBLISHING, claim_token = 새 UUID
  → claimed_at = now, available_at = now + stall_timeout
  → COMMIT (선점을 durable 하게)
  → transport.publish(envelope)
  → 성공: 같은 claim_token일 때만 PUBLISHED, claim_token 제거
  → 실패: attempt_count += 1, last_error 기록
       · attempt_count < max_attempts → status=PENDING, 지수 backoff
       · attempt_count >= max_attempts → status=DEAD (poison 격리)
```

| status | 의미 |
|---|---|
| `PENDING` | 발행 대기 (신규 또는 재시도 예정) |
| `PUBLISHING` | 어떤 Publisher가 선점 중. stall timeout 경과 시 회수 |
| `PUBLISHED` | 발행 완료 |
| `DEAD` | 재시도 한도 초과. 사람이 봐야 함 |

- backoff: `2 * 2^(attempt-1)` 초, 최대 3600초
- 기본 `max_attempts` = 8
- 여러 Publisher 동시 실행 가능 (`SKIP LOCKED`)
- 죽은 Publisher가 선점한 행은 `stall_timeout_seconds`(기본 300초) 후 자동 회수
- 회수 시 `claim_token`이 교체되므로 오래 걸린 이전 Publisher의 뒤늦은 성공·실패
  기록은 무시된다. transport 성공 직후 프로세스가 죽을 수 있으므로 전달 보장은
  여전히 at-least-once이며 Spring의 `eventId` 중복 제거는 필수다.

---

## 6. Transport

Spring의 수신 방식이 확정되지 않아 **transport를 port로 분리**했다. 하나로 고정하지 않았다.

```python
class OutboxTransport(Protocol):
    def publish(self, message: OutboxMessage) -> None: ...
```

| 구현체 | 용도 | 설정 |
|---|---|---|
| `FakeOutboxTransport` | 테스트/드라이런. 기본값 | `OUTBOX_TRANSPORT=fake` |
| `HttpCallbackTransport` | Spring endpoint로 POST | `OUTBOX_TRANSPORT=http`, `OUTBOX_HTTP_ENDPOINT`, `OUTBOX_HTTP_AUTH_HEADER` |
| SQS transport | **미구현** | Spring 수신 방식 확정 후 추가 |

`HttpCallbackTransport`는 body에 위 envelope JSON을 그대로 담아 POST한다.
**2xx가 아니면 실패로 간주**하고 재시도한다. 따라서 Spring은 **중복 수신에 안전한
멱등 endpoint**를 제공해야 한다.

---

## 7. Spring 담당자 결정 필요 사항

1. **수신 방식**: HTTP callback인가, SQS인가?
2. HTTP라면 **endpoint URL과 인증 헤더**.
3. **멱등 처리**: `eventId` 중복 제거 테이블을 어디에 둘 것인가?
4. **타임아웃/재시도 정책**: Spring이 느리면 Python이 재시도한다. 허용 응답 시간은?
5. **실패 UI**: `PIPELINE_FAILED` 수신 시 사용자에게 무엇을 보여줄 것인가?
6. `DEAD` 이벤트 모니터링/알림 주체는 누구인가?
