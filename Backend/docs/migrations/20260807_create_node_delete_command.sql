-- Pending node delete state is retained independently from the graph projection.
-- The project, member, and outbox identifiers follow their existing INT primary keys.

CREATE TABLE node_delete_command (
    id BIGINT NOT NULL AUTO_INCREMENT,
    command_id VARCHAR(36) NOT NULL,
    outbox_id INT NULL,
    project_id INT NOT NULL,
    expected_graph_version BIGINT NOT NULL,
    requested_by_member_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    reason_code VARCHAR(50) NULL,
    result_event_id VARCHAR(36) NULL,
    result_graph_version BIGINT NULL,
    requested_node_count INT NOT NULL,
    merged_source_count INT NOT NULL DEFAULT 0,
    total_node_count INT NOT NULL,
    requested_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    updated_at DATETIME(6) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    CONSTRAINT uk_node_delete_command_command_id
        UNIQUE (command_id),
    CONSTRAINT uk_node_delete_command_outbox_id
        UNIQUE (outbox_id),
    CONSTRAINT uk_node_delete_command_result_event_id
        UNIQUE (result_event_id)
);

CREATE INDEX idx_node_delete_command_project_status
    ON node_delete_command (project_id, status);

CREATE INDEX idx_node_delete_command_status_requested_at
    ON node_delete_command (status, requested_at);

CREATE TABLE node_delete_command_item (
    id BIGINT NOT NULL AUTO_INCREMENT,
    node_delete_command_id BIGINT NOT NULL,
    node_id VARCHAR(36) NOT NULL,
    expected_node_version BIGINT NOT NULL,
    item_type VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_node_delete_command_item_command_node
        UNIQUE (node_delete_command_id, node_id),
    CONSTRAINT fk_node_delete_command_item_command
        FOREIGN KEY (node_delete_command_id) REFERENCES node_delete_command(id)
);

CREATE INDEX idx_node_delete_command_item_node
    ON node_delete_command_item (node_id, node_delete_command_id);

-- outbox_id is nullable because the outbox uses an IDENTITY key and may be attached
-- after the pending command is first constructed. No FK targets project_node_projection:
-- command items remain as audit/status data after projection replacement removes nodes.
