# 자동 Graph 개요

```text
SQS/STT/정규화
→ Candidate와 서버 검증 Evidence
→ Decision-first Embedding/Retrieval/B 모델
→ Action/Issue 부모 해석
→ Graph Mutation Plan 안전 게이트
→ 단일 transaction 적용
```

외부 호출은 Graph 적용 transaction 밖에서 수행한다. B 모델 결과는 제안이며
서버의 project/category/type/version/parent/threshold 검증을 통과한 변경만
반영한다. 정확한 규칙은
[`../contracts/automatic-node-merge.md`](../contracts/automatic-node-merge.md)를
따른다.
