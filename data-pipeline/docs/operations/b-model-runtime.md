# B 모델 런타임 (GmsBModelClient)

**상태**: 운영 어댑터 구현 완료. 실제 GMS 호출로 MERGE/LINK/CREATE_NEW 판정 검증됨 (2026-08-01 라이브 E2E).

## 1. 구성

```text
Analysis Worker
  → execute_b_model(client=GmsBModelClient, ...)
      → prompt asset "b-model-recommendation-v1" 렌더 (SHA 잠금)
      → OpenAI 호환 chat/completions (response_format=json_object)
      → JSON decision → BModelDecision 검증 (서버)
      → _validate_target: target 존재/project 동일/type 호환/version 일치
```

`build_b_model_client()`는 `B_MODEL_ADAPTER=gms`(별칭 `openai`)일 때 어댑터를 만들고,
그 외에는 **명확한 설정 오류**(RuntimeError)로 기동을 막는다. `NotImplementedError`는 제거됐다.

## 2. 환경변수 (fallback 체인 문서화)

| 변수 | fallback | 기본값 |
|---|---|---|
| `B_MODEL_ADAPTER` | — | (없으면 기동 오류) |
| `B_MODEL_API_KEY` | `GMS_KEY` | — |
| `B_MODEL_BASE_URL` | `OPENAI_BASE_URL` | — |
| `B_MODEL_NAME` | `OPENAI_MODEL` | — |
| `B_MODEL_TEMPERATURE` | — | `0.0` (`none` 문자열로 비활성) |
| `B_MODEL_TIMEOUT_SECONDS` | — | `120` |
| `B_MODEL_RETRY_COUNT` | — | `2` |
| `B_MODEL_RETRY_BACKOFF_SECONDS` | — | `0.5` |

fallback 규칙: B 모델 전용 값이 있으면 그것이 이기고, 없으면 기존 GMS 값으로 내려간다.

## 3. 오류 분류

| 상황 | 동작 |
|---|---|
| 408/409/425/429/5xx | 제한된 retry (지수 backoff) |
| 401/403 등 그 외 4xx | **즉시 실패** (재시도 무의미) |
| 2xx인데 JSON 아님 / choices 없음 / content 없음 | `BModelResponseError` 즉시 실패 |
| decision의 `targetNodeId`가 retrieval 후보 목록 밖 | `BModelResponseError` 즉시 실패 |
| 네트워크 timeout | retry 후 `BModelTransportError` |

모든 클라이언트 예외는 `execute_b_model`에서 `BModelExecutionError`로 래핑되고
run에 `B_MODEL_FAILED` 등이 기록된다. Analysis Worker에서는 retryable로 분류된다.

## 4. 보안

- `BModelClientSettings.api_key`는 `field(repr=False)` — traceback/log에 노출되지 않음
- 렌더된 prompt, 전체 response, transcript는 로그에 남기지 않음
- prompt에 injection guard 포함: transcript 내 지시문을 명령으로 취급하지 않음

## 5. 판정 규칙 (prompt asset 요지)

- `CREATE_NEW` / `LINK`(+`relationType`) / `MERGE` 중 하나
- targetNodeId는 후보 목록의 nodeId만
- **MERGE 보수적**: similarity가 높다는 이유만으로 MERGE 금지, 같은 키워드·다른 목적 = 다른 노드
- MERGE는 같은 nodeType만
- `sameMeetingSuggestedParent: true` 후보는 강한 참고 신호 — 단 target이 `ACTIVE`가 아니면
  `ATTACHED_TO` 판정 금지(검증에서 무효), 그 경우 CREATE_NEW + reason 언급
- 근거 부족 시 CREATE_NEW (잘못된 병합 > 누락)

## 6. 실측 결과 (라이브 E2E, dp_test DB)

| source | 판정 | 결과 |
|---|---|---|
| "회의 처리 서버는 EC2 사용" DECISION | **MERGE** → 기존 동일 결정 | 200, MergeHistory 1, source MERGED |
| "EC2에서 RDS 연결" ACTION | **LINK ATTACHED_TO** → EC2 결정 | (재분석 후) 200, CONFIRMED relation, ACTIVE |
| "SQS 확인 완료" ACTION | **CREATE_NEW** | 409 — 아래 제약 참조 |
| 회의 B "S3 정적 호스팅" DECISION | **CREATE_NEW** | 200, ACTIVE |
| 회의 B 후보들 → EC2 결정 false merge | 없음 (0건) | ✓ |

## 7. 알려진 제품 규칙 제약 (코드로 우회하지 않음)

1. **부모 없는 ACTION/ISSUE는 CREATE_NEW/RELATED_TO 최종 승인이 불가능하다** (409
   "Action/Issue requires a valid ATTACHED_TO parent" / "RELATED_TO does not satisfy…").
   합법적 종결: analysis candidate를 reject하고 노드를 UNATTACHED로 유지.
   Spring UI는 이 경로("보류/미연결 유지")를 제공해야 한다.
2. **병합이 target version을 올리면 그 target을 가리키던 형제 후보는 stale**해진다.
   회복 경로: `POST /nodes/{id}/reanalyze` → 새 attempt 생성(이번 작업에서 수정) → 재승인.
