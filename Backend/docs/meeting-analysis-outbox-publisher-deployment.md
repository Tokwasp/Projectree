# Meeting Analysis Command Outbox Publisher 배포

## 선행 확인

`FOR UPDATE SKIP LOCKED`를 사용하므로 운영 DB가 MySQL 8 이상인지 먼저 확인한다.

```sql
SELECT VERSION();
```

기존 Outbox Row가 있으면 요청자 ID를 payload에서 추정하거나 임의의 Member ID로 채우지 않는다.
감사 로그 등 신뢰 가능한 원천이 없으면 해당 Row의 처리 정책을 데이터 소유자와 결정한 뒤 배포한다.

## 적용 순서

1. Publisher를 비활성화한 상태로 애플리케이션을 배포한다.
2. `20260804_alter_meeting_analysis_command_outbox_for_publisher.sql`의 nullable 컬럼 추가와 기존 PENDING 예약 시각 설정까지 적용한다.
3. 기존 Row의 `requested_by_member_id`를 신뢰 가능한 원천으로 backfill한다.
4. null 검증 결과가 0일 때만 NOT NULL과 인덱스 변경을 적용한다.
5. `20260804_create_meeting_analysis_notification_outbox.sql`을 적용한다.
6. 전용 Standard Queue URL, Region, IAM 권한을 설정한다.
7. 한 인스턴스에서 Publisher를 활성화해 확인한 뒤 전체 인스턴스로 확대한다.

## Claim 인덱스 확인

```sql
EXPLAIN
SELECT *
FROM meeting_analysis_command_outbox
WHERE (
        status = 'PENDING'
        AND next_attempt_at <= CURRENT_TIMESTAMP(6)
        AND attempt_count < 3
      )
   OR (
        status = 'PUBLISHING'
        AND lease_until <= CURRENT_TIMESTAMP(6)
      )
ORDER BY created_at ASC, id ASC
LIMIT 20
FOR UPDATE SKIP LOCKED;
```

Optimizer가 데이터 분포에 따라 두 인덱스 중 하나 또는 index merge를 선택하는지 확인한다.

## 설정

필수 설정은 `MEETING_ANALYSIS_PUBLISHER_ENABLED=true`,
`MEETING_ANALYSIS_COMMAND_QUEUE_URL`, `AWS_REGION`이다. 자격 증명은 IAM Role 또는
AWS SDK Default Credentials Chain으로만 제공한다.
