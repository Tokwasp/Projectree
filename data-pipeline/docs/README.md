# 문서 구조

| 경로 | 내용 |
|---|---|
| `CANDIDATE_NODE_CONFIRMATION_CONTRACT.md` | 구현보다 우선하는 Node 검토·확정 계약 |
| `contracts/` | Spring/Python API, Outbox, SQS·OpenVidu 메시지 계약 |
| `operations/` | FastAPI, Worker, B 모델, AWS 실행·운영 방법 |
| `handoffs/` | 다른 팀 담당자에게 전달할 경계와 미구현 범위 |
| `reports/` | 시점이 고정된 E2E·품질 검증 결과 |

런타임 동작을 바꿀 때는 계약을 먼저 확인하고, 실행 방법은
`operations/`, 과거 측정 결과는 `reports/`에서 찾는다.

