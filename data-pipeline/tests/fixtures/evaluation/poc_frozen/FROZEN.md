# poc_frozen — 동결 원본 (읽기 전용)

poc-node-extraction repo(PoC 1·2차)에서 **복사**해 온 동결 자산이다. **수정 금지 / 참조 전용.**
M1 파이프라인 코드는 이 디렉터리를 import 하지 않는다. 회귀 비교·정답 기준·라벨링 규칙의
근거로만 사용한다.

| 경로 | 내용 | 출처 |
| --- | --- | --- |
| `scorer/v3_evaluator.py` | PoC 채점기 (가중 이분 매칭 + graphPrecisionStrict + coverage + lifecycle) | PoC src |
| `scorer/evidence_evaluator.py` | evidence 대조/정규화 (normalize_quote 등) | PoC src |
| `gold/*.json` | 정답셋 5회의(M1/M2/M2X/M2Y/M3) items·judgments + registry_decisions | PoC poc_dataset/gold |
| `라벨링_가이드_초안.md` | 경계 사례 판정 규칙 R1~R9 (LLM 판단 지침의 근거) | PoC |
| `노드생성_파이프라인_인터페이스_정의서_v1.md` | IF-0~IF-6 인터페이스 정의 | PoC |

## 왜 동결인가
- gold 는 재현성의 기준선이다. M1 에서 손대면 PoC 결과와의 비교가 무의미해진다.
- 채점기는 PoC 지표(graphPrecisionStrict 등)를 그대로 재현하기 위한 원본이다.
- M2 에서 프롬프트를 v2.2 계약으로 재작성할 때, 이 gold·가이드가 판단 지침의 출발점이 된다.

## M1 과의 관계
- M1 의 검증 로직(`data_pipeline/validation/`)은 이 채점기를 **문자열 복사하지 않고 규칙만 수확**해
  v2.2 계약으로 재작성했다. 원본은 여기 동결로 남겨 대조 가능하게 둔다.
- `normalize_quote` 규칙은 `data_pipeline/validation/normalize.py` 로 재작성됐다(동일 동작).
