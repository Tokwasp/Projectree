CREATE TABLE meeting_summary_projection (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    meeting_id INT NOT NULL,
    project_id INT NOT NULL,
    command_id CHAR(36) NOT NULL,
    meeting_summary_id CHAR(36) NOT NULL,
    summary_version INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    api_path VARCHAR(500) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    synced_at DATETIME(6) NOT NULL,

    CONSTRAINT uk_meeting_summary_projection_meeting
        UNIQUE (meeting_id)
);

CREATE INDEX idx_meeting_summary_projection_project
    ON meeting_summary_projection(project_id, synced_at);

CREATE INDEX idx_meeting_summary_projection_command
    ON meeting_summary_projection(command_id);
