# 사용자 확정형 MVP 정책

1. LLM이 생성한 모든 노드는 `PROPOSED`로 저장한다.
2. `PROPOSED`는 그래프 검색·추론의 정식 노드로 취급하지 않는다.
3. 사용자는 제목, 타입, 부모 관계를 수정할 수 있다.
4. 사용자가 승인하면 `CONFIRMED`로 전환하고 그래프에 반영한다.
5. 사용자가 삭제하면 `REJECTED`로 보존하거나 물리 삭제 정책을 따른다.
6. 부모가 없는 확정 Action/Issue는 `UNATTACHED`로 저장한다.
7. 부모가 `PROPOSED`, `MINUTES_ONLY`, `REJECTED`이면 ATTACH를 확정할 수 없다.
8. Minutes 생성 실패는 노드 검토와 확정을 롤백하지 않는다.
