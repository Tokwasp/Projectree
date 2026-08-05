# 자동 Graph 라벨링 가이드

라벨 한 줄은 다음 JSONL 계약을 사용한다.

```json
{
  "caseId": "case-001",
  "projectId": "15",
  "sourceNodeId": "UUID",
  "expectedAction": null,
  "expectedTargetNodeId": null,
  "expectedParentNodeId": null,
  "labelStatus": "UNREVIEWED",
  "notes": null
}
```

상태:

- `CONFIRMED`: 사람이 Evidence와 그래프 문맥을 확인한 공식 평가 라벨
- `DISPUTED`: 검토자 간 합의가 되지 않은 사례
- `WEAK_LABEL`: 과거 merge/relation 이력에서 유도한 참고 라벨
- `UNREVIEWED`: 아직 검토하지 않은 queue

공식 의미 품질 지표에는 `CONFIRMED`만 사용한다. `WEAK_LABEL`과
`UNREVIEWED`를 정답으로 간주하지 않는다. 검토 과정에 본문이나 Evidence가
필요하면 접근 제한 파일로 분리하고 일반 summary에는 넣지 않는다.
