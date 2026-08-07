CREATE TABLE meeting_analysis_result_inbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_schema_version INT NOT NULL,
    event_id CHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    project_id INT NOT NULL,
    meeting_id INT NULL,
    command_id CHAR(36) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    processed_at DATETIME(6) NOT NULL,

    CONSTRAINT uk_meeting_analysis_result_event_id
        UNIQUE (event_id)
);

CREATE INDEX idx_meeting_analysis_result_command
    ON meeting_analysis_result_inbox(command_id);

CREATE INDEX idx_meeting_analysis_result_meeting
    ON meeting_analysis_result_inbox(meeting_id, processed_at);
