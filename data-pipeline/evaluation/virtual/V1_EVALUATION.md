# V1 단일 실행 평가 가이드

## 목적

남은 크레딧으로 자동 확정 성능을 반복 최적화하지 않는다.

이번 테스트의 합격 기준은 다음이다.

> 한 번의 전체 파이프라인 실행으로 사용자가 최종 승인·수정할 수 있는 후보를 충분히 제공하는가?

모델 결과는 전부 `PROPOSED`로 취급한다. 테스트 결과가 좋아도 자동으로
`CONFIRMED` 그래프에 넣지 않는다.

## 실행

```bash
python scripts/compare_pipeline_profiles.py \
  --segments evaluation/virtual/V1_segments.json \
  --profiles poc-lts \
  --env-file .env \
  --out outputs/pipeline_compare_V1
```

추출 1회 + 판단 1회, 총 LLM 2회 호출이다.

## 평가 순서

1. 결과를 보기 전 `V1_gold.json`을 수정하지 않는다.
2. `extraction.json`에서 잡담 과추출과 gold 후보 누락을 확인한다.
3. `judgment.json`에서 확정 Decision 누락과 개인 계획 오확정을 확인한다.
4. 모든 ATTACH의 부모가 실제 생성되는 Decision인지 확인한다.
5. 사용자가 다음 조작만으로 최종 그래프를 만들 수 있는지 본다.
   - 승인
   - 제목/타입 수정
   - 부모 변경
   - 삭제
   - 부모 없는 Action/Issue 유지

## 합격 기준

- gold 노드 13개 중 11개 이상이 승인 가능한 후보로 존재
- 확정 Decision 6개 중 5개 이상 후보로 존재
- 점심·축구·커피 잡담 노드 0개
- dangling ATTACH 0개
- 결과 전부 PROPOSED

판단 enum이 정확하지 않더라도 사용자가 1~2번의 수정으로 올바른 노드로
만들 수 있으면 후보 생성 관점에서는 성공으로 본다.

## 제품 방향

이 테스트를 통과하면 프롬프트 반복 수정은 중단하고 다음 UI/API를 우선한다.

- 제안 노드 목록
- 일괄 승인
- 제목·타입 수정
- 부모 Decision 변경
- 노드 삭제
- 부모 없는 Action/Issue 보관
- 승인된 노드만 CONFIRMED 그래프 반영
