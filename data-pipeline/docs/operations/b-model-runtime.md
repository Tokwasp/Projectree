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

## 3. 오류 분류

| 상황 | 동작 |
|---|---|
| 408/409/425/429/5xx | 제한된 retry (지수 backoff) |
| 401/403 등 그 외 4xx | **즉시 실패** (재시도 무의미) |
| 2xx인데 JSON 아님 / choices 없음 / content 없음 | `BModelResponseError` 즉시 실패 |
| decision의 `targetNodeId`가 retrieval 후보 목록 밖 | `BModelResponseError` 즉시 실패 |
| 네트워크 timeout | retry 후 `BModelTransportError` |

자동 Plan에서 클라이언트·응답 검증 오류가 나면 해당 항목을 `CREATE_NEW`로
강등하고 warning을 남긴다. 레거시 Analysis Worker는 기존
`BModelExecutionError` 재시도 계약을 유지한다.

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
