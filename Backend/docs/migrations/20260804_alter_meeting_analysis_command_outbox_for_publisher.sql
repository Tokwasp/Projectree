-- 기존 Row의 요청자 정보는 Outbox payload만으로 복구할 수 없다.
-- 아래 첫 단계는 nullable로 컬럼을 추가하며, 운영 데이터 소유자가 감사 로그 등 신뢰 가능한
-- 원천으로 requested_by_member_id를 backfill한 뒤 NOT NULL 전환을 수행해야 한다.

ALTER TABLE meeting_analysis_command_outbox
    ADD COLUMN requested_by_member_id INT NULL AFTER attempt_count,
    ADD COLUMN next_attempt_at DATETIME(6) NULL AFTER requested_by_member_id,
    ADD COLUMN lease_until DATETIME(6) NULL AFTER next_attempt_at,
    ADD COLUMN claim_token VARCHAR(36) NULL AFTER lease_until;

-- 신규 PENDING Row는 애플리케이션에서 현재 시각을 기록한다.
-- 기존 PENDING Row는 배포 시점부터 발행 가능하도록 아래 값을 명시적으로 설정한다.
UPDATE meeting_analysis_command_outbox
SET next_attempt_at = CURRENT_TIMESTAMP(6)
WHERE status = 'PENDING'
  AND next_attempt_at IS NULL;

-- 신뢰 가능한 요청자 원천으로 backfill한 뒤 0건인지 확인한다.
SELECT COUNT(*) AS missing_requested_by_member_id
FROM meeting_analysis_command_outbox
WHERE requested_by_member_id IS NULL;

-- 위 결과가 0일 때만 실행한다.
ALTER TABLE meeting_analysis_command_outbox
    MODIFY COLUMN requested_by_member_id INT NOT NULL;

DROP INDEX idx_meeting_analysis_outbox_publish
    ON meeting_analysis_command_outbox;

CREATE INDEX idx_meeting_analysis_outbox_pending
    ON meeting_analysis_command_outbox (
        status,
        next_attempt_at,
        created_at,
        id
    );

CREATE INDEX idx_meeting_analysis_outbox_expired_lease
    ON meeting_analysis_command_outbox (
        status,
        lease_until,
        created_at,
        id
    );
