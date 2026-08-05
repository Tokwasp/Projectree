# 실제 검토 E2E — 결과와 발견 사항

**실행일**: 2026-08-01, **RUN_ID**: `20260801-31f48041`
**환경**: 로컬 PostgreSQL 16(pgvector), 실제 GMS Candidate LLM + 실제 GMS Embedding + 실제 GMS B 모델
**산출물**: `outputs/node-review-e2e/20260801-31f48041/`

## 1. 검증된 전체 흐름

```text
실제 LLM Candidate 생성 (candidate-quality-v1)
→ PostgreSQL 저장 (4후보: ISSUE/DECISION/ACTION×2, lifecycle TODO/COMPLETED)
→ FastAPI 후보 목록/수정(409 확인)/project 격리 확인
→ initial-review/complete → 202 + analysis_job 4건
→ Analysis Worker (실제 embedding + 실제 B 모델) → 4/4 SUCCEEDED
→ pgvector retrieval_result (seed 그래프 3노드 대상)
→ 실제 B model result → final-review API
→ approve-merge → 200 (MergeHistory 1, source MERGED, Evidence 보존)
→ approve-create (DECISION) → 200 (ACTIVE)
→ reanalyze → 새 attempt → approve-link → 200 (ATTACHED_TO CONFIRMED, parent 설정,
   lifecycle TODO 보존)
→ Outbox: ANALYSIS_QUEUED/INITIAL_REVIEW_READY/FINAL_REVIEW_READY/GRAPH_CHANGED
```

false merge: **0건** (무관 결정 0건, 회의 B 동일 키워드·다른 목적 0건).
provider 호출: candidate LLM 10회, embedding ~17회, B 모델 ~11회 (비용 기록, key/prompt 미기록).

## 2. 이번 E2E가 발견한 결함과 조치

### F1. 짧은 quote 1개가 확정 결정을 통째로 무효화 (원인: 실제 모델 행동)
- 7자 quote("네, 좋습니다.") 하나가 붙자 EVIDENCE_INVALID → DECISION MINUTES_ONLY 강등
  → ATTACH 자식 2건 연쇄 강등. 4후보 중 3후보 소실.
- 강등 규칙은 잠긴 정책(위조 근거 차단) → 유지. **prompt에서 원인 차단** + 재실행으로 4/4 생존 확인.

### F2. 강등이 완전 무음 (코드 결함 → 수정)
- `ValidationResult.demoted`가 계산되고 버려짐 — `request.warnings`는 빈 배열.
- 수정: `DEMOTED:<itemId>:<rule>`을 request.warnings에 영속 + 회귀 테스트.

### F3. 부모 없는 ACTION/ISSUE의 최종 승인 불가 (제품 규칙 — 문서화)
- CREATE_NEW → 409 "Action/Issue requires a valid ATTACHED_TO parent",
  LINK RELATED_TO → 409 "RELATED_TO does not satisfy the parent requirement".
- 유일한 종결: reject 후 UNATTACHED 유지. B prompt에 반영(ACTIVE 아닌 target에 ATTACHED_TO 금지),
  Spring UI 요구사항으로 handoff에 기록.

### F4. 병합 후 형제 후보 영구 고착 (코드 결함 → 수정)
- MERGE 승인 → target version 1→2 → 같은 target을 가리키던 형제 후보 "Candidate target is
  no longer valid". reanalyze가 **같은 input hash의 COMPLETED run을 재사용**(created=false)해
  stale 후보가 영원히 남음.
- 수정: `reanalyze_unattached_node`가 PENDING 후보의 target 드리프트를 감지하면 재사용을
  거부하고 **새 attempt** 생성 (`_pending_candidate_target_is_stale`). 회귀 테스트 + 라이브 재현으로
  created=true → 재분석 → approve-link 200 확인.

### F5. superseded run의 stale 후보가 final-review에 노출 (코드 결함 → 수정)
- 재분석 후에도 옛 PENDING 후보가 목록에 남아 보장된 409로 유도.
- 수정: `build_final_review`가 `Node.current_analysis_run_id`의 후보만 노출.
  (옛 후보는 DB에 보존 — 감사/직접 reject 가능.)

## 3. 남는 운영 특성 (설계 확인 사항)

- **순서 의존 승인**: 한 회의 안에서 MERGE를 먼저 승인하면 같은 target의 다른 후보는
  reanalyze가 필요하다. Spring UI는 409 시 "재분석" 버튼(`POST /nodes/{id}/reanalyze`)을 제공할 것.
- **parent hint와 승인 순서**: 같은 회의 parent가 아직 UNATTACHED면 B 모델은 ATTACHED_TO를
  낼 수 없다(검증 무효). 부모(DECISION)를 먼저 최종 승인하면 자식 재분석에서 LINK가 가능해진다.
- reanalyze로 생기는 옛 PENDING 후보는 자동 정리되지 않는다(감사 목적 보존).

## 4. 재현 방법

```powershell
# 폐기용 DB 준비 후
$env:DATABASE_URL="postgresql+psycopg://pipeline:***@localhost:5432/dp_test_..."
$env:EMBEDDING_ADAPTER="gms"; $env:B_MODEL_ADAPTER="gms"
python -m alembic upgrade head
# scratchpad/node_review_e2e.py 참조 (스크립트 사본은 산출물 디렉터리 참고)
python tests/tools/evaluation/evaluate_candidate_quality.py --actual tests/fixtures/evaluation/candidate_quality/actual-20260801 --out report.json
python tests/tools/evaluation/evaluate_candidate_quality.py --live --out report-live.json   # opt-in
```
