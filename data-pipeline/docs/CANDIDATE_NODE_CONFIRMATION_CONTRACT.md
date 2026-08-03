# Candidate 검토 및 Node 확정 계약

- 제품 경로 상태: **레거시 호환 계약**
- 현재 자동 제품 계약:
  [`contracts/automatic-node-merge.md`](contracts/automatic-node-merge.md)
- 운영/스테이징에서는 이 문서의 사용자 1차·최종 승인 API가 기본 비활성이다.
  기존 호출자 전환과 로컬 회귀 검증을 위해 구현은 당분간 보존한다.

- 상태: **확정**
- 확정일: 2026-07-30
- 적용 범위: Candidate 1차 검토, UNATTACHED Node 분석, Retrieval, B 모델 추천, 최종 신규 확정·연결·병합
- 우선순위: 이 범위에서는 `NEXT_TEAM_WORK.md`와 `DATA_PIPELINE_SOLO_ROADMAP.md`의 이전 설명보다 이 문서가 우선한다.

## 1. 핵심 원칙

1. LLM 결과는 자동으로 확정 그래프에 반영하지 않는다.
2. Candidate 내용에 대한 1차 검토와 Node의 최종 승인을 분리한다.
3. 1차 검토를 통과한 Candidate는 `UNATTACHED Node`가 된다.
4. Retrieval과 B 모델은 추천만 생성하며 Node나 Relation을 직접 변경하지 않는다.
5. 최종 변경은 사용자의 명시적인 승인으로만 수행한다.
6. 비즈니스 용어 `CONFIRMED Node`는 DB의 `graph_state=ACTIVE`를 의미한다.
7. Evidence는 normalizedText를 사용하되 rawText와 원래 출처를 보존한다.

## 2. 용어

### Candidate

LLM이 회의에서 추출한 임시 결과다.

- 아직 Node가 아니다.
- 사용자는 제목, 본문, 유형, 카테고리, Evidence 등을 수정할 수 있다.
- 1차 검토 완료 전까지 편집할 수 있다.
- 거절되거나 회의록으로만 보존되는 Candidate는 Node를 만들지 않는다.

### UNATTACHED Node

Candidate의 내용에 대한 사용자 1차 검토가 완료되어 DB에 생성된 Node다.

- Node 형태로 저장된다.
- 최종 확정 Node가 아니다.
- 기존 Node와의 구조 관계, 의미 관계, 병합 여부가 아직 확정되지 않았다.
- Retrieval 및 B 모델 분석 대상이다.

### CONFIRMED Node

Retrieval과 B 모델 결과를 확인한 사용자가 최종 승인한 Node를 뜻하는 비즈니스 용어다.

```text
비즈니스 명칭: CONFIRMED Node
DB 저장 상태: graph_state = ACTIVE
```

`CONFIRMED`라는 별도 DB `graph_state` 값은 추가하지 않는다.

### MERGED Node

다른 Node에 내용이 통합된 Node다.

- 물리적으로 삭제하지 않는다.
- `graph_state=MERGED`로 변경한다.
- `merged_into_node_id`로 병합 대상을 기록한다.
- 원래 Evidence와 출처를 계속 보존한다.

## 3. 전체 상태 흐름

```text
Candidate(PENDING)
→ 사용자 편집
→ complete_initial_review
→ Node(UNATTACHED, analysis_status=PENDING)
→ Retrieval
→ 필요한 경우 B 모델
→ Node(UNATTACHED, analysis_status=ANALYZED)
→ 사용자 최종 승인
   ├─ 신규 확정: ACTIVE
   ├─ 연결 후 확정: ACTIVE + Relation
   └─ 병합: source=MERGED, target=ACTIVE
```

분석 이후 Node가 수정되면 다음과 같이 처리한다.

```text
UNATTACHED / ANALYZED
→ Retrieval 입력 필드 수정
→ UNATTACHED / STALE
→ 사용자가 reanalyze_unattached_node 실행
→ UNATTACHED / PENDING
→ Retrieval/B 모델
→ UNATTACHED / ANALYZED
```

수정 중에는 자동 분석하지 않는다.

## 4. Candidate 1차 검토

`complete_initial_review`는 Candidate 내용 검토를 완료하는 동작이다.

이때 서버는 다음을 수행한다.

1. Candidate의 사용자 검토값을 확정한다.
2. Candidate를 출처로 하는 Node를 정확히 하나 생성한다.
3. 생성 Node의 `graph_state`를 `UNATTACHED`로 저장한다.
4. 생성 Node의 `analysis_status`를 `PENDING`으로 저장한다.
5. NodeEvidence를 생성하되 normalizedText 기반 quote를 저장한다.
6. 기존 Node와 Relation을 생성하거나 병합하지 않는다.
7. Candidate와 생성된 UNATTACHED Node의 연결을 기록한다.

동일 요청이 다시 들어오면 새 Node를 중복 생성하지 않고 기존 Node를 반환한다.

Candidate의 `APPROVED`는 다음 의미로만 사용한다.

```text
Candidate 내용의 1차 검토 완료
≠ Node의 최종 확정
```

### Decision-first 분석 순서

1차 검토는 모든 승인 Candidate를 UNATTACHED Node로 만들지만 분석 Job은
다음 순서로 해제한다.

```text
Decision 존재
→ Decision만 분석
→ 모든 Decision 사용자 최종 결정
→ Action/Issue 분석

Decision 없음
→ Action/Issue 즉시 분석
```

Decision의 분석 Run 완료나 추천 Candidate 생성만으로는 Decision 단계가
완료되지 않는다. source Decision이 사용자의 CREATE_NEW/LINK로 `ACTIVE`가
되거나 MERGE로 `MERGED`가 되어야 완료다. MERGE된 Decision을 부모로 제안했던
Action/Issue는 `merged_into_node_id` 계보를 따라 같은 프로젝트의 최종 canonical
Node를 분석 후보로 사용한다. 단계 해제는 기존 Node별 AnalysisJob 구조를
유지하며 meeting 잠금과 `AnalysisJob.node_id` UNIQUE로 멱등 처리한다.

## 5. Node 유형별 구조 규칙

기존 부모 유효성 규칙을 유지한다.

### Decision

- 구조적 부모 없이 `ACTIVE`가 될 수 있다.

### Action

- `ACTIVE Decision`을 부모로 하는 유효한 `ATTACHED_TO`가 있어야 `ACTIVE`가 될 수 있다.

### Issue

- `ACTIVE Decision` 또는 `ACTIVE Action`을 부모로 하는 유효한 `ATTACHED_TO`가 있어야 `ACTIVE`가 될 수 있다.

다음 문장은 이 계약의 필수 규칙이다.

> `RELATED_TO`는 독립된 Node 사이의 비구조적 의미 관계이며, Action과 Issue의 부모 조건을 충족하지 않는다. Action과 Issue의 구조적 부모 관계에는 기존 `ATTACHED_TO`를 유지하며, 유효한 `ATTACHED_TO` 부모가 없는 Action과 Issue는 `ACTIVE`로 최종 확정할 수 없다.

## 6. 관계 유형

### ATTACHED_TO

- 구조적 부모 관계다.
- 방향성이 있다.
- `Action → Decision`, `Issue → Decision|Action`에 사용한다.
- target은 `ACTIVE` 상태여야 한다.
- source를 `ACTIVE`로 전환할 때 부모 유형과 상태를 서버가 검증한다.

### RELATED_TO

- 두 독립 Node 사이의 비구조적 의미 관계다.
- 방향성이 없다.
- Action/Issue의 부모 조건을 충족하지 않는다.
- source와 target을 모두 유지한다.
- DB 중복 방지를 위해 두 UUID를 정렬한 canonical pair를 사용한다.

MVP에서 새로 추가하는 의미 관계는 `RELATED_TO` 하나로 시작한다. `SUPPORTS`, `DEPENDS_ON`, `SUPERSEDES` 등의 세분화는 실제 사용 데이터를 확인한 후 결정한다.

## 7. Retrieval 계약

### 검색 입력

Candidate가 아니라 1차 검토된 UNATTACHED Node의 현재 값을 사용한다.

```text
node_type
category
title
content
normalized Evidence
```

### 검색 범위

다음 조건을 모두 만족해야 한다.

- 같은 `project_id`
- `graph_state IN (ACTIVE, UNATTACHED)`
- 현재 검색 Node 자신이 아님
- `MERGED`, `EXCLUDED`, `ARCHIVED`가 아님

현재 회의와 이전 회의의 UNATTACHED Node를 모두 검색할 수 있다.

MERGED Node는 검색 결과로 직접 노출하지 않는다. 필요하면 병합 계보를 따라 최종 canonical Node를 사용한다.

### 저장 정보

```text
analysis_run_id
source_node_id
source_node_version
analysis_input_hash
embedding model/version
retrieval config version
Top-K
result node ID/version/rank/similarity
실행 시각
```

## 8. B 모델 계약

B 모델은 현재 UNATTACHED Node와 Retrieval 결과를 비교하여 다음 중 하나를 추천한다.

```text
CREATE_NEW
LINK
MERGE
```

추천 결과에는 최소한 다음 정보가 포함된다.

```json
{
  "recommendation": "LINK",
  "targetNodeId": "550e8400-e29b-41d4-a716-446655440000",
  "relationType": "RELATED_TO",
  "reason": "같은 주제와 관련되지만 서로 다른 결정을 나타냄"
}
```

모든 Node ID는 UUID 문자열이다.

B 모델은 Node, Relation, Evidence를 직접 변경하지 않는다.

Retrieval 결과가 없으면 B 모델 호출을 생략할 수 있다.

```text
analysis_status = ANALYZED
b_model_status = SKIPPED
b_model_skip_reason = NO_RETRIEVAL_CANDIDATES
```

B 모델 호출이 실패해도 Retrieval 결과가 유효하면 사용자는 직접 최종 결정을 내릴 수 있다.

```text
analysis_status = ANALYZED
b_model_status = FAILED
```

## 9. 분석 상태와 무효화

### 전체 분석 상태

| 상태 | 의미 |
| --- | --- |
| `PENDING` | 분석 대기 또는 실행 준비 |
| `ANALYZING` | 현재 분석 실행이 RUNNING이며 처리 중 |
| `ANALYZED` | Retrieval 완료, B 모델도 성공·생략·실패 중 하나의 종료 상태 |
| `STALE` | 분석 후 입력 Node가 변경되어 과거 결과가 무효 |
| `FAILED` | Retrieval 자체가 실패하여 유효한 분석 결과가 없음 |

### 분석 실행 상태

Node의 `analysis_status`는 최신 분석을 요약하고, `NodeAnalysisRun.status`는 개별 실행 이력을 나타낸다.

| 실행 상태 | 의미 |
| --- | --- |
| `PENDING` | 실행 레코드가 생성되어 worker 처리를 기다림 |
| `RUNNING` | worker가 실행을 선점하여 처리 중 |
| `COMPLETED` | 유효한 분석이 정상 종료됨 |
| `FAILED` | 해당 attempt가 실패함 |
| `SUPERSEDED` | Node 입력이나 Retrieval 설정이 바뀌어 더 이상 현재 실행이 아님 |

기본 전이는 다음과 같다.

```text
Node: PENDING → ANALYZING → ANALYZED
Node: PENDING/ANALYZING → FAILED
Node: PENDING/ANALYZING/ANALYZED/FAILED → 입력 수정 시 STALE
Node: STALE/FAILED → reanalyze 요청 시 PENDING

Run: PENDING → RUNNING → COMPLETED
Run: PENDING/RUNNING → FAILED
Run: PENDING/RUNNING/COMPLETED → 입력 무효화 시 SUPERSEDED
```

`reanalyze_unattached_node()`는 Retrieval이나 B 모델을 직접 호출하지 않는다. 현재 Node version과
입력 해시를 기준으로 PENDING 실행을 만들고 `node.current_analysis_run_id`를 갱신한다.

- 동일 Node version·동일 입력 해시의 PENDING/RUNNING 실행은 기존 실행을 멱등 반환한다.
- 동일 입력의 COMPLETED 실행도 새로 실행하지 않고 기존 결과를 반환한다.
- FAILED 실행만 `attempt + 1`로 재시도한다.
- 분석 상태와 실행 상태만 변경할 때는 `Node.version`을 증가시키지 않는다.
- Node 입력이 수정되면 Node version을 증가시키고 현재 실행을 SUPERSEDED로 보존한다.

PostgreSQL은 애플리케이션의 Node row lock과 별도로 다음 무결성을 강제한다.

- `(source_node_id, analysis_input_hash)`에 대해 `PENDING/RUNNING` Run은 최대 하나다.
- `Node.current_analysis_run_id`는 반드시 해당 Node 자신의 Run만 가리킨다.
- Retrieval 결과의 `target_node_version`은 1 이상이다.

`retrieval_config_version`은 거리 계산법, Top-K, 검색 상태 필터, tie-break 정책이 바뀔 때 반드시
증가시킨다. 임베딩 모델과 임베딩 버전은 별도 필드로 저장하고 `analysis_input_hash`에도 포함하여,
운영자가 Retrieval 설정 버전 증가를 놓쳐도 다른 임베딩 결과가 같은 분석으로 재사용되지 않게 한다.

### B 모델 상태

```text
PENDING
SUCCEEDED
SKIPPED
FAILED
```

### analysisInputHash

`contentHash`보다 범위가 명확한 `analysis_input_hash`를 사용한다.

해시에는 다음 값을 결정적인 순서로 포함한다.

```text
node_type
category
title
content
정렬된 Evidence(segment_id, normalized quote)
Retrieval 설정 버전
```

다음 필드가 변경되면 Node version을 증가시키고 기존 분석을 `STALE` 처리한다.

- 제목
- 본문
- Node 유형
- 카테고리
- Evidence 내용
- 기타 Retrieval 입력 필드

화면 표시 순서, UI 설정, 검색에 사용하지 않는 사용자 메모는 분석을 무효화하지 않는다.

## 10. 최종 승인 API

모든 API는 같은 프로젝트인지, 현재 상태와 version이 요청값과 같은지, 분석 결과가 현재 Node를 기준으로 생성되었는지 검증한다.

### approve_create_new

UNATTACHED Node를 독립 Node로 확정한다.

```json
{
  "sourceNodeId": "550e8400-e29b-41d4-a716-446655440000",
  "sourceExpectedVersion": 3,
  "analysisRunId": "f739132d-2f8b-46a8-9387-a4e328f930e0"
}
```

서버 규칙:

```text
Decision
→ 구조적 부모 없이 허용

Action/Issue
→ 유효한 ATTACHED_TO 부모가 이미 있을 때만 허용
→ 부모가 없거나 부모가 ACTIVE가 아니면 거부
```

일반적인 Action/Issue 확정은 `approve_link_existing(ATTACHED_TO)`를 사용한다.
여기서 “이미 유효한 ATTACHED_TO 부모”란 target이 `ACTIVE`이고, 부모 유형이
허용되며, 저장된 `parent_id`와 `ATTACHED_TO` Relation이 서로 일치하는 경우다.
`approve_create_new`는 이 관계를 새로 만들거나 잘못된 관계를 보정하지 않는다.
이 허용 규칙은 기존·이관 데이터와 사전에 구조 관계가 준비된 Node를 위한 호환 경로다.

### approve_link_existing

두 Node를 유지하면서 관계를 생성하고 source Node를 최종 확정한다.

```json
{
  "sourceNodeId": "550e8400-e29b-41d4-a716-446655440000",
  "targetNodeId": "92452d19-c327-4d22-97ce-b751beb76689",
  "relationType": "RELATED_TO",
  "sourceExpectedVersion": 3,
  "targetExpectedVersion": 7,
  "analysisRunId": "f739132d-2f8b-46a8-9387-a4e328f930e0"
}
```

`ATTACHED_TO` 승인:

```text
source = UNATTACHED Action/Issue
target = 유형이 유효한 ACTIVE 부모
→ ATTACHED_TO 생성
→ source.parent_id 설정
→ source를 ACTIVE로 전환
```

`RELATED_TO` 승인:

```text
source와 target을 모두 유지
→ RELATED_TO 생성
→ target 상태는 변경하지 않음
→ source가 유형별 구조 규칙을 이미 충족하면 ACTIVE
→ source Action/Issue에 유효한 부모가 없으면 승인 거부
```

특히 다음 규칙을 적용한다.

```text
source UNATTACHED + target UNATTACHED + RELATED_TO
→ target은 UNATTACHED 유지
→ source는 자신의 구조 규칙을 충족할 때만 ACTIVE
```

### approve_merge_existing

source UNATTACHED Node의 내용을 target Node에 통합한다.

```json
{
  "sourceNodeId": "550e8400-e29b-41d4-a716-446655440000",
  "targetNodeId": "92452d19-c327-4d22-97ce-b751beb76689",
  "mergedTitle": "사용자가 승인한 최종 제목",
  "mergedContent": "사용자가 승인한 최종 본문",
  "sourceExpectedVersion": 3,
  "targetExpectedVersion": 7,
  "analysisRunId": "f739132d-2f8b-46a8-9387-a4e328f930e0"
}
```

서버 검증:

- source는 `UNATTACHED`여야 한다.
- target은 `ACTIVE` canonical Node여야 한다.
- source와 target은 같은 프로젝트에 속해야 한다.
- source와 target은 서로 달라야 한다.
- source와 target의 Node 유형이 같아야 한다.
- source와 target의 현재 version이 요청 version과 같아야 한다.
- source 또는 target이 이미 `MERGED`이면 거부한다.
- analysisRunId와 현재 source의 analysis_input_hash가 일치해야 한다.
- target은 같은 project/category/type의 ACTIVE canonical Node여야 한다.
- target을 ACTIVE로 만들 때 target의 유형별 구조 규칙도 충족해야 한다.

적용 결과:

```text
target.id 유지
target.title/content = mergedTitle/mergedContent
target.version 증가
target = ACTIVE
source = MERGED
source.merged_into_node_id = target.id
양쪽 Evidence는 원래 Node에 유지
병합 이력과 GraphChangeEvent 기록
target embedding 재생성 요청
```

## 11. Evidence 계약

### 표시와 저장

```text
사용자 표시: normalizedText
Retrieval/B 모델 입력: normalizedText
원문 검증과 감사: rawText
```

rawText와 normalizedText는 TranscriptSegment에 함께 저장한다.

NodeEvidence는 normalized quote와 원래 회의·세그먼트 정보를 유지한다.

### 병합 시 Evidence

Evidence 행을 target Node로 복사하거나 이동하지 않는다.

```text
최종 Node의 전체 Evidence
= target 자신의 Evidence
+ target으로 병합된 MERGED Node들의 Evidence
```

병합 체인이 존재하면 최종 canonical Node까지 계보를 따라 전체 Evidence를 조회한다.

## 12. 병합 계보와 감사

Node에는 현재 병합 대상을 빠르게 찾기 위한 `merged_into_node_id`를 둔다.

감사 추적을 위해 별도 `node_merge_history`를 둔다.

최소 저장 항목:

```text
source_node_id
target_node_id
approved_by
approved_at
source_version
target_version
merged_title
merged_content
analysis_run_id
```

병합된 source Node를 다시 병합할 수 없다. target이 나중에 다른 Node로 병합되면 계보를 따라 최종 canonical Node를 찾으며 순환은 허용하지 않는다.

## 13. 동시성·멱등성

최종 승인 트랜잭션에서는 다음을 보장한다.

- source와 target을 잠그고 version을 비교한다.
- 같은 승인 요청이 재전송되어도 Node, Relation, 이력, outbox가 중복되지 않는다.
- 자기 자신에 대한 연결·병합을 거부한다.
- 다른 프로젝트 Node에 대한 연결·병합을 거부한다.
- source나 target의 version이 달라지면 전체 요청을 거부한다.
- 승인 도중 오류가 발생하면 Node, Relation, merge history, GraphChangeEvent, outbox 변경을 전부 rollback한다.
- embedding과 B 모델 같은 외부 호출은 승인 DB 트랜잭션 안에서 실행하지 않는다.

## 14. 필수 저장 구조

최소한 다음 구조가 필요하다.

```text
Node
- merged_into_node_id
- analysis_status
- analysis_input_hash
- initial_reviewed_by / initial_reviewed_at
- confirmed_by / confirmed_at

NodeAnalysisRun
- source_node_id / source_node_version
- analysis_input_hash
- retrieval 상태와 설정
- B 모델 상태와 생략·실패 사유

RetrievalResult
- analysis_run_id
- target_node_id / target_node_version
- rank / similarity

MergeRecommendation
- analysis_run_id
- recommendation / target_node_id / relation_type
- raw/parsed response
- model/prompt/usage/latency

NodeMergeHistory
- source/target/승인자/승인시각/version/최종 내용
```

Candidate가 만든 Node를 가리키는 필드는 `confirmed_node_id`보다 `initial_review_node_id`가 정확하다. 기존 데이터와 호환해야 한다면 새 필드를 추가·이관한 뒤 기존 필드를 점진적으로 폐기한다.

## 15. 공개 서비스 경계

```text
edit_candidate
complete_initial_review

edit_unattached_node
reanalyze_unattached_node

approve_create_new
approve_link_existing
approve_merge_existing
```

기존 `approve_candidate()`와 `bulk_approve_candidates()`는 신규 흐름 내부에서 사용하지 않는다. 호환 기간에는 deprecated wrapper로 유지할 수 있으나 새 서비스 경계를 우회해서는 안 된다.

## 16. 완료 조건

- Candidate 1차 검토만으로 ACTIVE Node나 Relation이 생성되지 않는다.
- Candidate 하나에서 UNATTACHED Node가 중복 생성되지 않는다.
- Retrieval은 같은 프로젝트의 ACTIVE와 UNATTACHED만 검색한다.
- Retrieval은 검색 Node 자신과 MERGED Node를 제외한다.
- B 모델은 그래프를 직접 변경하지 않는다.
- B 모델 생략·실패 시에도 사용자가 최종 처리를 계속할 수 있다.
- 최종 승인 당시 source와 target version 및 analysis_input_hash를 다시 검증한다.
- RELATED_TO는 Action/Issue의 구조 부모로 인정되지 않는다.
- 유효한 ACTIVE 부모가 없는 Action/Issue는 ACTIVE가 될 수 없다.
- UNATTACHED target은 RELATED_TO만으로 자동 ACTIVE가 되지 않는다.
- 병합 시 source Node와 Evidence를 삭제하지 않는다.
- 최종 Node의 Evidence 조회에서 병합된 source Evidence가 함께 보인다.
- 중복 요청과 동시 요청에도 Node, Relation, Evidence, 감사 이력이 중복되지 않는다.
- 모든 상태 변경은 GraphChangeEvent 또는 전용 감사 이력으로 추적된다.

## 17. 범위 제외

초기 MVP에서는 다음을 제외한다.

- 사용자 승인 없는 자동 연결·병합
- 복잡한 의미 관계 유형 세분화
- MERGED Node를 일반 Retrieval 후보로 노출
- 의미 변화 여부를 판단하기 위한 추가 LLM 호출
- 동일 분석 내용에 대한 범용 캐시
- 별도 Vector DB 또는 Neo4j 도입

## 최종 요약

> Candidate는 LLM이 만든 임시 결과다. 사용자의 1차 검토가 완료되면 UNATTACHED Node가 되고, ACTIVE 및 UNATTACHED Node를 대상으로 Retrieval과 B 모델 추천을 수행한다. 사용자는 최종적으로 신규 확정, 구조적 연결, 의미 관계 연결 또는 병합을 승인한다. `ATTACHED_TO`는 Action/Issue의 구조적 부모 관계이고 `RELATED_TO`는 부모 조건을 충족하지 않는 비구조적 의미 관계다. 비즈니스 용어 CONFIRMED는 DB의 ACTIVE를 뜻한다. 병합은 기존 target ID를 유지하면서 source를 MERGED로 보존하고, Evidence는 원래 Node에 둔 채 병합 계보를 통해 함께 조회한다.
