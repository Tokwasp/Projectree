# 자동 Node 생성·흡수 병합 계약

상태: 현재 제품 계약 (Result Event v3)

## 처리 순서

정규화 Transcript 이후 운영 Orchestrator는 Candidate를 생성·검증한 뒤 Decision을 먼저 확정하고 Action/Issue를 처리한다. B 모델의 출력은 명령이 아니라 제안이며 Retrieval 점수, margin, 동일 project/category/node type, identity, conflict, target 상태와 version을 서버가 다시 검증한다. 조건 하나라도 실패하면 해당 항목만 `CREATE_NEW`로 강등한다.

## 흡수 병합

자동 `MERGE`의 source는 이번 분석에서 생성한 `UNATTACHED` leaf이고 target은 같은 project/category/node type의 삭제되지 않은 `ACTIVE` canonical Node다.

성공 시 하나의 Graph transaction에서 다음을 수행한다.

1. B 모델의 검증된 `suggestedTitle`, `suggestedContent`로 target의 새 `NodeRevision`을 만든다.
2. target의 title/content와 version을 갱신하고 기존 READY Embedding을 STALE로 만든다.
3. source는 `MERGED`, `mergedIntoNodeId=target`, `parentNodeId=null`이 된다.
4. source Evidence와 `MergeOperation`은 보존한다.
5. Graph version은 전체 mutation plan에 대해 정확히 한 번 증가한다.
6. Full Snapshot v1에는 target `ACTIVE`와 source `MERGED`, Evidence, merge record를 모두 포함한다.

같은 plan에서 여러 source가 한 target으로 합쳐지면 target revision과 version은 source마다 순서대로 증가하며, 이후 source 검증은 그 plan이 만든 target version 증가를 허용한다. 외부 동시 수정은 허용하지 않는다.

## 관계와 삭제

Decision은 구조적 부모 없이 ACTIVE일 수 있다. Action은 ACTIVE Decision, Issue는 ACTIVE Decision 또는 Action을 부모로 가져야 한다. `RELATED_TO`는 이 부모 조건을 충족하지 않는다.

삭제는 leaf-only다. 자식이 있으면 `409 NODE_HAS_CHILDREN`이며 자식을 UNATTACHED로 바꾸지 않는다. 대표 Node 삭제 시 연결된 MERGED source도 같은 transaction에서 soft delete한다. MERGED source 직접 삭제 및 삭제 복원은 지원하지 않는다.

## Legacy 기능

수동 MERGE/UNMERGE/REMERGE 코드는 호환성 목적으로 유지하되 기본 비활성이다. `ENABLE_LEGACY_MANUAL_MERGE_API=true`인 명시적 환경에서만 endpoint가 동작하며 신규 자동 제품 경로는 호출하지 않는다.
