# 자동 Graph Pilot 평가

Pilot은 기존 canonical `ACTIVE/UNATTACHED` Node ID를 최대 50건 추출해 실제
Retrieval 코드를 read-only로 실행한다. 제목·본문·Evidence·vector는 일반
결과에 기록하지 않는다.

평가 전후 `node`, `relation`, `node_revision`, `evidence`,
`node_revision_evidence`, `merge_operation`, `generation_run`,
`node_analysis_run`, `outbox_event`의 row count와 PK checksum이 같아야 한다.

사람이 확정한 라벨이 없으면 precision, recall, F1, target accuracy는
`N/A — confirmed labels unavailable`이다. 이때 확인 가능한 것은 Retrieval
coverage, 후보 수, type validity, 오류율, latency와 threshold 계산 mechanics다.

Threshold simulator는 similarity, top1-top2 margin, B 모델 confidence 조합을
계산하지만 운영 설정을 변경하지 않는다. CONFIRMED 라벨이 300건 미만이면
`NOT_CALIBRATED`다.
