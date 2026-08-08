-- 자동 Migration 도구가 없으므로 기존 운영 DB에는 DBA 절차로 적용한다.
ALTER TABLE meeting_analysis_command_outbox
    MODIFY COLUMN meeting_id INT NULL,
    ADD COLUMN target_project_id INT NULL AFTER meeting_id,
    ADD COLUMN target_node_id VARCHAR(36) NULL AFTER target_project_id;

ALTER TABLE meeting_analysis_result_inbox
    MODIFY COLUMN meeting_id INT NULL;

-- 기존 uk_meeting_analysis_command_outbox_meeting_type(meeting_id, command_type)는 유지한다.
-- MySQL의 UNIQUE 제약은 NULL meeting_id 행을 여러 건 허용하며 command_id UNIQUE가
-- 각 노드 수정 명령의 고유성을 보장한다.
