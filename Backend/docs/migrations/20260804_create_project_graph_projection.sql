CREATE TABLE project_graph_sync (
    project_id INT NOT NULL,
    current_graph_version BIGINT NOT NULL DEFAULT 0,
    last_command_id CHAR(36) NULL,
    synced_at DATETIME(6) NOT NULL,
    PRIMARY KEY (project_id)
);

CREATE TABLE project_node_projection (
    node_id CHAR(36) NOT NULL,
    project_id INT NOT NULL,
    source_meeting_id INT NULL,
    parent_node_id CHAR(36) NULL,
    merged_into_node_id CHAR(36) NULL,
    node_type VARCHAR(20) NOT NULL,
    category VARCHAR(20) NOT NULL,
    graph_state VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    link_source VARCHAR(20) NULL,
    source_node_version BIGINT NOT NULL,
    source_created_at DATETIME(6) NOT NULL,
    source_updated_at DATETIME(6) NOT NULL,
    synced_at DATETIME(6) NOT NULL,
    PRIMARY KEY (node_id),
    INDEX idx_project_node_tree (project_id, graph_state, category),
    INDEX idx_project_node_parent (project_id, parent_node_id),
    INDEX idx_project_node_merged_target (project_id, merged_into_node_id),
    INDEX idx_project_node_source_meeting (source_meeting_id)
);

CREATE TABLE node_evidence_projection (
    evidence_id CHAR(36) NOT NULL,
    node_id CHAR(36) NOT NULL,
    meeting_id INT NOT NULL,
    quote_text TEXT NOT NULL,
    speaker_label VARCHAR(100) NULL,
    start_ms BIGINT NULL,
    end_ms BIGINT NULL,
    evidence_order INT NOT NULL,
    synced_at DATETIME(6) NOT NULL,
    PRIMARY KEY (evidence_id),
    CONSTRAINT fk_node_evidence_projection_node
        FOREIGN KEY (node_id) REFERENCES project_node_projection(node_id),
    INDEX idx_node_evidence_order (node_id, evidence_order),
    INDEX idx_node_evidence_meeting (meeting_id)
);
