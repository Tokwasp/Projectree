CREATE TABLE meeting_analysis_notification_outbox (
    id INT NOT NULL AUTO_INCREMENT,
    notification_id VARCHAR(36) NOT NULL,
    command_id VARCHAR(36) NOT NULL,
    meeting_id INT NOT NULL,
    project_id INT NOT NULL,
    recipient_member_id INT NULL,
    audience VARCHAR(20) NOT NULL,
    notification_type VARCHAR(64) NOT NULL,
    payload LONGTEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_meeting_analysis_notification_id
        UNIQUE (notification_id),
    CONSTRAINT uk_meeting_analysis_notification_command_audience_type
        UNIQUE (command_id, audience, notification_type)
);
