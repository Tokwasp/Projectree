# Prompt source map

실행 시 사용되는 잠금 자산은 `data_pipeline/prompts/assets/` 아래에 있다.

| PipelineProfile | Extraction | Judgment |
|---|---|---|
| `poc-lts` (기본) | `extraction_poc_v3_lts.md` | `judgment_poc_v4_lts.md` |
| `m2-current-candidate` | `extraction_m2_current.md` | `judgment_m2_current.md` |

이 디렉터리의 `prompt_1_extraction.md`, `prompt_2_judgment.md`는 초기 통합 시점 참고 복사본이다. 런타임에서 직접 읽지 않는다. prompt를 수정할 때는 참고 복사본이 아니라 assets manifest에 새 버전을 등록하고 SHA를 갱신해야 한다.

A LTS 원문은 수정하지 않는다. 현재 M2 prompt도 비교 재현을 위해 candidate 자산으로 보존한다.
