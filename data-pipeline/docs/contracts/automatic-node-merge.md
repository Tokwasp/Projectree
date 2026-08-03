# 자동 Node 생성·연결·병합 계약

- 상태: **현재 제품 계약**
- 기준 설계: `automatic-node-merge-design.md`
- 적용일: 2026-08-02
- 대체 범위: Candidate 1차 검토 및 사용자 최종 승인 중심의 제품 흐름

## 1. 제품 실행 흐름

```text
SQS → STT/정규화 → A 모델 Candidate/Evidence
→ 서버 Evidence 검증
→ Decision Embedding/Retrieval/B 모델
→ Decision canonical 확정
→ Action/Issue Embedding/Retrieval/B 모델
→ 전체 Graph Mutation Plan 검증
→ 한 PostgreSQL 트랜잭션으로 Node/Revision/Evidence/Relation/Merge 반영
→ GRAPH_GENERATION_COMPLETED Outbox
```

외부 STT·Embedding·LLM 호출은 최종 적용 트랜잭션 밖에서 수행한다. 최종
트랜잭션이 실패하면 이 실행의 그래프 변경과 완료 이벤트는 모두 rollback한다.

## 2. 상태 의미

- `ACTIVE`: 현재 canonical 그래프에 노출되는 Node.
- `UNATTACHED`: 유효한 Evidence는 있으나 Action/Issue의 필수 구조 부모를
  해결하지 못한 Node. 사용자 승인 대기 상태가 아니다.
- `MERGED`: 논리적으로 다른 Node를 가리키는 원본 Node. 삭제하지 않는다.
- `DELETED`: 사용자 soft delete 상태.
- `NEEDS_ATTENTION`: 사용자 구조 변경 뒤 수동 확인이 필요한 상태.

정상 Decision은 구조 부모 없이 `ACTIVE`가 될 수 있다. Action은 ACTIVE
Decision, Issue는 ACTIVE Decision 또는 Action에 `ATTACHED_TO`되어야 ACTIVE다.
`RELATED_TO`는 이 부모 조건을 충족하지 않는다.

## 3. Revision과 Evidence

- Node의 모든 의미 변경은 새 `NodeRevision`을 만든다.
- 자동 생성 Revision은 최소 한 개의 `TRANSCRIPT` Evidence가 필요하다.
- LLM이 보낸 quote를 그대로 저장하지 않는다. 서버가 프로젝트·회의 범위의
  `TranscriptSegment.normalized_text`와 offset을 검증하고 직접 잘라 저장한다.
- 사용자가 직접 만든 Node는 `USER_ASSERTION` Evidence를 사용한다.
- Evidence, Revision, 병합 원본은 물리적으로 덮어쓰거나 삭제하지 않는다.
- 기존 DB의 검증 불가능한 Evidence는 `LEGACY`로 이관하고 만들어내지 않는다.

## 4. 자동 판단과 안전 게이트

Decision을 먼저 판단하고 그 canonical 결과를 Action/Issue의 부모 후보에
사용한다. B 모델 출력은 서버 명령이 아니라 입력일 뿐이며 아래 검증을 모두
통과한 MERGE만 적용한다.

- Retrieval 1위 target
- 운영에서 보정한 절대 similarity 임계값 이상
- 1위와 2위의 보정된 margin 이상
- source/target Node type 동일
- source/target Category 동일 (`MERGE_CATEGORY_MISMATCH`)
- target이 ACTIVE canonical Node (`MERGE_TARGET_NOT_ACTIVE`)
- `identityBasis`의 필수 동일성 항목 모두 참
- `conflictsChecked`에 실제 충돌 검사 결과 존재
- Action은 source의 planned Decision과 기존 target Action의 부모를 각각 최종
  canonical Decision으로 해석했을 때 동일하며 due date가 충돌하지 않음
- 분석 때 기록한 target version이 적용 시점에도 동일

임계값이 설정되지 않았거나 어느 하나라도 실패하면 MERGE를 강행하지 않고
항목 단위 `CREATE_NEW`로 강등하고 warning을 기록한다. Embedding·Retrieval·B
모델 실패도 전체 회의를 버리지 않고 해당 항목을 보수적으로 격리한다.

### 4.1 MERGE 검색과 LINK 검색은 정책이 다르다

MERGE는 두 Node의 정체성을 하나로 접으므로 Category와 node_type이 **하드
필터**이고, ACTIVE canonical Node만 흡수할 수 있다(`search_merge_candidates`).

LINK도 구조적 부모 관계이므로 Category를 하드 필터로 사용한다
(`search_link_candidates`). 서로 다른 역할 Category의 Node는 같은 기능을
다루더라도 독립 Graph partition에 속하며 부모·자식으로 연결하지 않는다.

두 검색을 같은 정책으로 묶으면 둘 중 하나가 반드시 깨진다.

### 4.2 적용 단계의 이중 방어

Retrieval 범위 제한은 첫 번째 방어선일 뿐이다. 자동·수동 재분석은 모두
project/category/type/state 범위를 제한하지만, 적용 단계도 node_type과 Category를
다시 검증하고 어긋나면 거부한다. 따라서 stale 또는 위조된 후보가 들어와도
교차 Category 병합·부모 연결은 적용되지 않는다.

## 5. 논리 병합과 Relation

- 병합은 source를 `MERGED`로 바꾸고 `merged_into_node_id`를 target으로
  설정한다. target 제목·본문·Evidence는 자동으로 덮어쓰지 않는다.
- 동일 Graph Plan에서 여러 source가 하나의 canonical target으로 MERGE되면
  target version은 그룹 적용 시작 전에 외부 변경 검사용으로 검증한다. 같은
  그룹 안의 source는 Evidence의 가장 이른 원문 시간, segment ID, source item ID,
  source Node UUID 순으로 결정적으로 처리한다.
- 각 source는 독립된 `MergeOperation`과 UNMERGE/REMERGE 이력을 유지한다.
  자동 논리 병합은 어떤 Node 타입에서도 target Revision을 임의 변경하지 않는다.
- `MergeOperation`은 source/target revision·version, 판단 이유, Retrieval
  score, 모델 근거를 기록한다.
- Relation은 병합 전 원래 endpoint를 유지한다. 조회할 때 canonical resolver가
  병합 계보를 따라 최종 endpoint를 계산한다.
- 연쇄 병합은 `MergeOperationDependency`로 직접 의존성을 기록한다.
- UNMERGE는 최신 의존 Operation부터 역순으로만 허용한다. target의 후속 사용자
  편집은 되돌리지 않는다.
- canonical cycle, 다른 프로젝트, 다른 타입 병합, 자기 병합은 거부한다.

## 6. 멱등성·동시성·공개

```text
GenerationRun 멱등키
= project_id + meeting_id + recording_hash + pipeline_version
```

중복 SQS 입력은 같은 완료 Run을 재사용하며 Node, Relation, MergeOperation,
완료 Outbox를 중복 생성하지 않는다. 적용 직전 모든 외부 target을 일정한 UUID
순서로 잠그고 project와 version을 재확인한다. 사용자가 먼저 target을 수정했으면
자동 변경보다 사용자 변경을 우선하며 MERGE/LINK를 CREATE_NEW로 강등한다.

`COMPLETED` 또는 `COMPLETED_WITH_WARNINGS`가 된 뒤에만 일반 그래프 조회와
완료 알림에 결과를 노출한다. 실패 실행의 중간 Plan은 그래프에 남기지 않는다.

## 7. API와 레거시 경계

- 제품 API는 Graph 조회, Node 직접 생성·수정·soft delete, Relation 편집,
  MERGE/UNMERGE/REMERGE 및 GenerationRun 조회다.
- 사용자 수정은 LLM을 다시 호출하지 않으며 새 Revision과 감사 정보를 남긴다.
- Python PostgreSQL이 그래프 정본이다. Spring은 직접 DB를 수정하지 않는다.
- 모든 API는 `X-Project-Id` 범위를 검증한다. 운영/스테이징은
  `X-Internal-Service-Token`이 필수이며 private network 배치를 전제로 한다.
- 기존 Candidate 검토·재분석·승인 API는 이전 호출자 전환용 호환 경로다.
  운영/스테이징에서는 기본 비활성이고 자동 SQS 제품 흐름에서 호출하지 않는다.

## 8. 운영 전 반드시 확정할 값

- 최소 300개 라벨 사례로 `AUTO_MERGE_MIN_SIMILARITY`와
  `AUTO_MERGE_MIN_MARGIN` 보정
- Spring과 `project_id`, `meeting_id`, `actor_id`, `request_id` 계약 및 토큰 전달
- 기존 ACTIVE Node Embedding backfill
- 실제 Clova/GMS/Embedding 실패율·timeout·credit 관측과 경보

값을 보정하기 전에도 자동 생성은 동작하지만 자동 MERGE는 안전하게 비활성화된다.
