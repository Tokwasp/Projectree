ALTER TABLE project_graph_sync
    ADD COLUMN active_command_id VARCHAR(36) NULL,
    ADD COLUMN active_command_type VARCHAR(50) NULL,
    ADD COLUMN active_since DATETIME(6) NULL;

INSERT INTO project_graph_sync (
    project_id,
    current_graph_version,
    last_command_id,
    synced_at,
    active_command_id,
    active_command_type,
    active_since
)
SELECT
    project.id,
    0,
    NULL,
    CURRENT_TIMESTAMP(6),
    NULL,
    NULL,
    NULL
FROM project
LEFT JOIN project_graph_sync
    ON project_graph_sync.project_id = project.id
WHERE project_graph_sync.project_id IS NULL;
