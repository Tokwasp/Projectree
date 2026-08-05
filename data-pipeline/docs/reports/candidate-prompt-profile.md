# Candidate Prompt Profile — candidate-quality-v1

**상태**: 등록 완료(CANDIDATE), 기본값은 여전히 `poc-lts`. **동결 LTS 자산은 무수정.**

## 1. 프로필 구성

| 항목 | 값 |
|---|---|
| extraction | `extraction-candidate-quality-v1` (cq-1.0.1, SHA 잠금) |
| judgment | `judgment-candidate-quality-v1` (cq-1.0.0, SHA 잠금) |
| rendering | `M2_CURRENT` (기존 placeholder 재사용) |
| judgment adapter | `IDENTITY` (서버 enum 직접 출력) |
| 활성화 | `PIPELINE_PROMPT_PROFILE=candidate-quality-v1` (워커) 또는 `run_meeting(prompt_profile=...)` |

기본 프로필은 바뀌지 않았다. 환경변수가 비어 있으면 기존과 완전히 동일하게 동작한다.
워커 기동 시 잘못된 프로필명은 즉시 실패한다(런타임에서 eager 검증).

## 2. LTS 대비 추가된 규칙

### ACTION lifecycleStatus (시제 보존)
```text
"하겠습니다/할게요"        → TODO
"하고 있습니다/진행 중"    → IN_PROGRESS
"했습니다/확인했습니다"    → COMPLETED
"취소했습니다/않기로 했다" → CANCELLED
불명확                     → null (기본값 TODO 폴백 + needs-review 표시)
```
DECISION/ISSUE에는 null. 서버(`_candidate_lifecycle_status`)가 enum 밖 값을 무시하므로
모델이 이상값을 내도 안전하다.

### 회의 진행 잡음 제외
인사·감사, 재질문, 마이크/음량/발화 겹침, "다시 말해 달라", 근거 없는 추측, 일반 대화.
라이브 검증: "마이크가 겹쳐서…" 세그먼트가 후보에서 제외됨 (noise 0건).

### 불확실 기술어 보존
STT가 불명확한 기술어를 임의 고유명사로 확정 금지("오픈 리더" → OpenLidar 확정 금지).
확정 근거가 없으면 원문 표기 유지. warning 전용 컬럼은 만들지 않았다(지시서 §3).
라이브 검증: noise_heavy 시나리오에서 false canonicalization 0건.

### 프로젝트 진행 회의 기준
개인의 명확한 업무 선언은 **팀 동의가 없어도 ACTION** (제거 판정 없음 — UNATTACHED로 보존).
완료 보고도 COMPLETED ACTION으로 추출. 단순 가능성·아이디어는 DECISION 확정 금지.

### evidence 계약 강조 (라이브 E2E에서 발견된 실패로부터)
> "10자 미만 quote가 하나라도 섞이면 그 항목 전체가 무효 처리된다.
> '네, 좋습니다.' 같은 짧은 동의 발화는 quote로 추가하지 마라."

첫 라이브 실행에서 실제 모델이 7자 quote를 부가 근거로 붙여 **확정 DECISION이 통째로
MINUTES_ONLY 강등**되고 ATTACH 자식 2건이 연쇄 강등됐다. 강등 규칙 자체는 잠긴 제품
정책(위조 근거 차단)이므로 유지하고, prompt에서 원인을 차단했다. 재실행에서 4/4 생존.

## 3. 품질 결과 (실제 GMS, 2026-08-01)

| 시나리오 | recall | noise | lifecycle | parent | false canon |
|---|---|---|---|---|---|
| meeting_a (offline, 캡처본) | 1.0 | 0.0 | 1.0 (TODO/COMPLETED) | 1.0 | 0 |
| meeting_a (live) | 1.0 | 0.0 | 1.0 | 1.0 | 0 |
| tense_variety (live) | 1.0 | 0.0 | 1.0 (4종 전부) | — | 0 |
| noise_heavy (live) | 1.0 | 0.0 | 1.0 | 1.0 | 0 |

목표: recall≥95%, noise≤2%, lifecycle≥90%, parent Top-K≥95%, false merge=0 — **전부 충족**
(현재 gold set 기준. gold는 3개 시나리오로 작으므로 확대 필요).

평가 도구: `tests/tools/evaluation/evaluate_candidate_quality.py`
- `--actual DIR` 캡처본 offline 평가 (CI-safe, provider 호출 없음)
- `--live` opt-in 실제 provider 평가 (GMS_KEY 없으면 blocked로 종료)
- gold: `tests/fixtures/evaluation/candidate_quality/gold/*.json`

## 4. 관측성 개선

강등이 무음이던 문제를 수정: 이제 `request.warnings`에
`DEMOTED:<itemId>:<rule>` (예: `DEMOTED:m2:EVIDENCE_INVALID`)가 영속된다.
식별자와 규칙명만 기록하며 회의 내용은 담지 않는다.
