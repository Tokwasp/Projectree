CREATE TABLE meeting_record (
    meeting_record_id BIGINT NOT NULL AUTO_INCREMENT,
    meeting_id INT NOT NULL,
    command_id CHAR(36) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary TEXT NULL,
    decisions TEXT NULL,
    next_todos TEXT NULL,
    issues TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,

    PRIMARY KEY (meeting_record_id),

    CONSTRAINT uk_meeting_record_meeting
        UNIQUE (meeting_id),

    CONSTRAINT uk_meeting_record_command
        UNIQUE (command_id),

    CONSTRAINT fk_meeting_record_meeting
        FOREIGN KEY (meeting_id)
        REFERENCES meeting (id)
);
