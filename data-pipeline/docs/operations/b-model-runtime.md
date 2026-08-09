# B 모델 런타임 (GmsBModelClient)

**상태**: 운영 어댑터 구현 완료. 실제 GMS 호출로 MERGE/LINK/CREATE_NEW 판정 검증됨 (2026-08-01 라이브 E2E).

## 1. 구성

```text
Automatic SQS Worker
  → Decision-first Graph Plan(client=GmsBModelClient, ...)
      → prompt asset "b-model-recommendation-v1" 렌더 (SHA 잠금)
      → OpenAI 호환 chat/completions (response_format=json_object)
      → JSON decision → BModelDecision 검증 (서버)
      → _validate_target: target 존재/project 동일/type 호환/version 일치
```

`build_b_model_client()`는 `B_MODEL_ADAPTER=gms`(별칭 `openai`)일 때 실제
어댑터를 만든다. 테스트 통합에서는 `fake`를 사용한다.

## 2. 환경변수 (fallback 체인 문서화)

| 변수 | fallback | 기본값 |
|---|---|---|
| `B_MODEL_ADAPTER` | — | 테스트 `fake`, 실제 `gms`/`openai` |
| `B_MODEL_API_KEY` | `GMS_KEY` | — |
| `B_MODEL_BASE_URL` | `OPENAI_BASE_URL` | — |
| `B_MODEL_NAME` | `OPENAI_MODEL` | — |
| `B_MODEL_TEMPERATURE` | — | `0.0` (`none` 문자열로 비활성) |
| `B_MODEL_TIMEOUT_SECONDS` | — | `120` |
| `B_MODEL_RETRY_COUNT` | — | `2` |
| `B_MODEL_RETRY_BACKOFF_SECONDS` | — | `0.5` |

fallback 규칙: B 모델 전용 값이 있으면 그것이 이기고, 없으면 기존 GMS 값으로 내려간다.

### 2.1 provider model과 실행 라벨은 다른 것이다

`resolve_provider_model()`(`b_model/gms.py`)이 `B_MODEL_NAME -> OPENAI_MODEL`
체인의 **유일한** 구현이며, 그 결과만 GMS 요청 body의 `model`에 들어간다.

| 개념 | 값 예시 | 어디에 쓰이나 |
|---|---|---|
| provider model | `gpt-5.2` | GMS 요청 `model`, `b_model_result.model` |
| pipeline label | `automatic-b-model` | 실행 경로 식별자. `b_model_result.metadata_json.pipelineLabel` |
| model_version | `automatic-v1` | 분석/프롬프트 계약 버전. `b_model_result.model_version` |

`recommend()`에는 모델 인자가 **없다**. provider model은 클라이언트 설정이지
호출자의 선택이 아니며, 필요하면 `client.provider_model`로 읽는다. 2026-08-05
회귀에서 호출부가 실행 라벨을 `model` 인자로 넘겨 GMS가 400을 반환했고, 이
인자를 제거해 같은 실수를 타입 수준에서 막았다.

## 3. 오류 분류

| 상황 | 동작 | failure code |
|---|---|---|
| 408/409/425/429/5xx | 제한된 retry (지수 backoff) 후 실패 | `B_MODEL_HTTP_ERROR` |
| 400/401/403/404 등 그 외 4xx | **즉시 실패** (재시도 무의미) | `B_MODEL_HTTP_ERROR` |
| 2xx인데 JSON 아님 / choices 없음 / content 없음 | 즉시 실패 | `B_MODEL_INVALID_RESPONSE` |
| decision의 `targetNodeId`가 retrieval 후보 목록 밖 | 즉시 실패 | `B_MODEL_INVALID_RESPONSE` |
| `BModelDecision` 계약 위반 | 즉시 실패 | `B_MODEL_VALIDATION_ERROR` |
| 네트워크 timeout | retry 후 실패 | `B_MODEL_TIMEOUT` |
| 연결/프로토콜 오류 | retry 후 실패 | `B_MODEL_TRANSPORT_ERROR` |
| 그 외 분류 불가 | 즉시 실패 | `B_MODEL_UNCLASSIFIED_ERROR` |

`B_MODEL_UNCLASSIFIED_ERROR`는 "네트워크 문제"라는 뜻이 **아니다**. 로컬 코드
버그(`AttributeError` 등)를 `B_MODEL_TRANSPORT_ERROR`로 기록하면 운영자가 엉뚱한
곳(GMS 상태·VPC·DNS)을 보게 되므로 별도 코드로 분리했다.

레거시 Analysis Worker 경로는 기존 코드를 유지한다 —
`B_MODEL_RESULT_INVALID`(REST 422로 매핑, `api/errors.py`)와
`B_MODEL_PERSISTENCE_FAILED`. 자동 경로의 `B_MODEL_VALIDATION_ERROR`와 의미가
같지만 계약이 이미 외부에 노출되어 있어 그대로 둔다.

retry 중 상태가 섞이면(예: 429 → connection reset) **provider가 실제로 응답한
쪽**을 보존한다. status code가 있는 오류가 없는 오류보다 우선한다.

HTTP 오류는 status, provider model, endpoint, request id, 그리고 GMS 응답
body에서 뽑아낸 **비민감 오류 메시지**(500자 제한, 개행 정리)를 예외에 담는다.
API Key·Authorization 헤더·렌더된 프롬프트·회의 원문은 절대 포함하지 않는다.

### 3.1 node_analysis_run 상태 규칙

| 상태 | 의미 |
|---|---|
| `SUCCEEDED` | 검증된 decision을 얻음 |
| `FAILED` | provider를 **호출했고** 정상 결과를 얻지 못함. `b_model_failure_code`/`b_model_failure_message` 필수 |
| `SKIPPED` | provider를 **호출하지 않음**. `b_model_skip_reason`만 채우고 failure 컬럼은 NULL |

`SKIPPED`의 사유는 `NO_RETRIEVAL_CANDIDATES`(후보 없음) 또는
`RETRIEVAL_FAILED`(검색 단계 실패, 이때 `retrieval_status`도 `FAILED`이고
`retrieval_completed_at`은 NULL)다. 외부 API 실패를 `SKIPPED`로 저장하지 않는다.
사유를 알 수 없으면 `UNKNOWN_SKIP_REASON` + `logger.error` — 그럴듯한 사유를
지어내지 않는다.

`node_analysis_run.status`는 자동 경로에서 항상 `COMPLETED`다(Node는 실제로
발행되었으므로). 대신 stage 실패는 run 레벨 `failure_code`/`failure_message`에도
기록되므로 아래 두 쿼리가 모두 동작한다.

```sql
SELECT * FROM node_analysis_run WHERE b_model_status = 'FAILED';
SELECT * FROM node_analysis_run WHERE failure_code IS NOT NULL;
```

**알려진 한계**: v3 coordinator 경로의 Java 이벤트(`PROJECT_GRAPH_CHANGED`)에는
아직 이 실패가 실리지 않는다. 이벤트 계약 변경은 Java 측 합의가 필요하다.

자동 Plan에서 B 모델이 실패하면 해당 항목은 회의 진행을 막지 않도록
`CREATE_NEW`로 강등되지만, run row는 `FAILED`로 남고 `generation_run.warnings`에
`B_MODEL_FAILED_CREATE_NEW`(+`failureCode`/`failureMessage`)가 기록되며
`logger.error`로도 남는다. 레거시 Analysis Worker는 기존 `BModelExecutionError`
재시도 계약을 유지한다.

## 4. 보안

- `BModelClientSettings.api_key`는 `field(repr=False)` — traceback/log에 노출되지 않음
- 렌더된 prompt, 전체 response, transcript는 로그에 남기지 않음
- prompt에 injection guard 포함: transcript 내 지시문을 명령으로 취급하지 않음

## 5. 판정 규칙 (prompt asset 요지)

- `CREATE_NEW` / `LINK`(+`relationType`) / `MERGE` 중 하나
- targetNodeId는 후보 목록의 nodeId만
- **MERGE 보수적**: similarity가 높다는 이유만으로 MERGE 금지, 같은 키워드·다른 목적 = 다른 노드
- MERGE는 같은 nodeType만
- `sameMeetingSuggestedParent: true`이고 `graphState=PLANNED`인 같은 회의
  Decision은 원자적 Plan 안에서 먼저 canonical 처리될 부모 후보
- MERGE는 구조화된 `identityBasis`와 `conflictsChecked`를 반드시 반환
- 근거 부족 시 CREATE_NEW (잘못된 병합 > 누락)

서버는 여기에 보정된 절대 similarity, 1·2위 margin, 타입·부모·due date,
적용 시점 target version을 다시 검증한다. `AUTO_MERGE_MIN_SIMILARITY` 또는
`AUTO_MERGE_MIN_MARGIN`이 비어 있으면 자동 MERGE는 CREATE_NEW로 강등된다.

## 6. 레거시 승인 흐름 실측 결과 (라이브 E2E, dp_test DB)

| source | 판정 | 결과 |
|---|---|---|
| "회의 처리 서버는 EC2 사용" DECISION | **MERGE** → 기존 동일 결정 | 200, MergeHistory 1, source MERGED |
| "EC2에서 RDS 연결" ACTION | **LINK ATTACHED_TO** → EC2 결정 | (재분석 후) 200, CONFIRMED relation, ACTIVE |
| "SQS 확인 완료" ACTION | **CREATE_NEW** | 409 — 아래 제약 참조 |
| 회의 B "S3 정적 호스팅" DECISION | **CREATE_NEW** | 200, ACTIVE |
| 회의 B 후보들 → EC2 결정 false merge | 없음 (0건) | ✓ |

## 7. 레거시 승인 흐름 제약

1. **부모 없는 ACTION/ISSUE는 CREATE_NEW/RELATED_TO 최종 승인이 불가능하다** (409
   "Action/Issue requires a valid ATTACHED_TO parent" / "RELATED_TO does not satisfy…").
   합법적 종결: analysis candidate를 reject하고 노드를 UNATTACHED로 유지.
   자동 제품 흐름에서는 사용자를 기다리지 않고 UNATTACHED로 보존한다.
2. **병합이 target version을 올리면 그 target을 가리키던 형제 후보는 stale**해진다.
   회복 경로: `POST /nodes/{id}/reanalyze` → 새 attempt 생성(이번 작업에서 수정) → 재승인.
