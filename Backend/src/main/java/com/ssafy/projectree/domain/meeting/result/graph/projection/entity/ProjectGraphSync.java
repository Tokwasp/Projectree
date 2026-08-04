package com.ssafy.projectree.domain.meeting.result.graph.projection.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "project_graph_sync")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ProjectGraphSync {

    @Id
    @Column(name = "project_id")
    private int projectId;

    @Column(name = "current_graph_version", nullable = false)
    private long currentGraphVersion;

    @Column(name = "last_command_id", length = 36)
    private String lastCommandId;

    @Column(name = "synced_at", nullable = false)
    private Instant syncedAt;

    public static ProjectGraphSync initial(int projectId, Instant syncedAt) {
        if (projectId <= 0) {
            throw new IllegalArgumentException("projectId must be positive");
        }
        ProjectGraphSync sync = new ProjectGraphSync();
        sync.projectId = projectId;
        sync.currentGraphVersion = 0;
        sync.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
        return sync;
    }

    public void advanceTo(long graphVersion, String commandId, Instant syncedAt) {
        if (graphVersion <= currentGraphVersion) {
            throw new IllegalArgumentException("graphVersion must advance current graph version");
        }
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("commandId must not be blank");
        }
        this.currentGraphVersion = graphVersion;
        this.lastCommandId = commandId;
        this.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
    }
}
