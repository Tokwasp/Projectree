# Test and validation area

제품 실행 코드는 `data_pipeline/`, 운영 유지보수 CLI는 `scripts/`에 둔다.
외부 호출 없는 자동 테스트와 수동 검증 자료는 이 디렉터리에 모은다.

```text
tests/
├── config/       # Fake adapter 환경 예시. production 사용 금지
├── fixtures/     # STT 응답, 계약 JSON, 평가 gold/segments
├── evaluation_support/ # 테스트와 평가 도구만 import하는 지원 코드
├── tools/
│   ├── evaluation/  # 품질 비교와 회귀 CLI
│   ├── integration/ # 로컬 음성·병합 경계 진단
│   └── smoke/       # 명시적 승인과 예산이 필요한 smoke 도구
├── evaluation/   # 평가 지원 코드의 pytest
├── operations/   # 운영 CLI의 안전성 pytest
└── test_*.py     # 제품 단위·통합 회귀
```

기본 `pytest`는 `NO_EXTERNAL_AI_CALLS=1`을 강제하며 실제 Clova/GMS를 호출하지
않는다. 수동 도구의 결과는 Git에서 제외된 `outputs/`에만 기록한다.
