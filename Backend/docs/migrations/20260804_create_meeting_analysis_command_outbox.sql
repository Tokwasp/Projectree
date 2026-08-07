-- 이 프로젝트에는 자동 Migration 도구가 없으므로 배포 시 DBA 절차로 적용한다.
-- 적용 전 meeting 테이블과 uk_meeting_room_name 제약 존재 여부를 확인한다.

CREATE TABLE meeting_analysis_command_outbox (
    id INT NOT NULL AUTO_INCREMENT,
    command_id VARCHAR(36) NOT NULL,
    meeting_id INT NOT NULL,
    command_type VARCHAR(64) NOT NULL,
    payload LONGTEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    requested_by_member_id INT NOT NULL,
    next_attempt_at DATETIME(6) NULL,
    lease_until DATETIME(6) NULL,
    claim_token VARCHAR(36) NULL,
    published_at DATETIME(6) NULL,
    last_error VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_meeting_analysis_command_outbox_command_id
        UNIQUE (command_id),
    CONSTRAINT uk_meeting_analysis_command_outbox_meeting_type
        UNIQUE (meeting_id, command_type),
    CONSTRAINT fk_meeting_analysis_command_outbox_meeting
        FOREIGN KEY (meeting_id) REFERENCES meeting (id)
);

CREATE INDEX idx_meeting_analysis_outbox_pending
    ON meeting_analysis_command_outbox (status, next_attempt_at, created_at, id);

CREATE INDEX idx_meeting_analysis_outbox_expired_lease
    ON meeting_analysis_command_outbox (status, lease_until, created_at, id);
