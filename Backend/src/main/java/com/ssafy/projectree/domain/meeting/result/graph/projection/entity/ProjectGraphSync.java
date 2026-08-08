package com.ssafy.projectree.domain.meeting.result.graph.projection.entity;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

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

    @Column(name = "active_command_id", length = 36)
    private String activeCommandId;

    @Enumerated(EnumType.STRING)
    @Column(name = "active_command_type", length = 50)
    private MeetingAnalysisCommandType activeCommandType;

    @Column(name = "active_since")
    private Instant activeSince;

    public static ProjectGraphSync initial(int projectId, Instant syncedAt) {
        if (projectId <= 0) {
            throw new IllegalArgumentException("projectId must be positive");
        }
        ProjectGraphSync sync = new ProjectGraphSync();
        sync.projectId = projectId;
        sync.currentGraphVersion = 0;
        sync.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
        sync.validateActiveCommandState();
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

    public boolean hasActiveCommand() {
        validateActiveCommandState();
        return activeCommandId != null;
    }

    public void acquireGraphOperation(
            String commandId,
            MeetingAnalysisCommandType commandType,
            Instant acquiredAt
    ) {
        validateCanonicalCommandId(commandId);
        Objects.requireNonNull(commandType, "commandType must not be null");
        validateGuardedCommandType(commandType);
        Objects.requireNonNull(acquiredAt, "acquiredAt must not be null");
        validateActiveCommandState();
        if (activeCommandId != null) {
            throw new IllegalStateException("Graph operation is already active");
        }

        activeCommandId = commandId;
        activeCommandType = commandType;
        activeSince = acquiredAt;
        validateActiveCommandState();
    }

    public boolean releaseGraphOperation(String commandId) {
        validateActiveCommandState();
        if (activeCommandId == null || !activeCommandId.equals(commandId)) {
            return false;
        }

        activeCommandId = null;
        activeCommandType = null;
        activeSince = null;
        validateActiveCommandState();
        return true;
    }

    @PrePersist
    @PreUpdate
    private void validateActiveCommandState() {
        boolean allNull = activeCommandId == null
                && activeCommandType == null
                && activeSince == null;
        boolean allPresent = activeCommandId != null
                && activeCommandType != null
                && activeSince != null;
        if (!allNull && !allPresent) {
            throw new IllegalStateException(
                    "Graph operation fields must be all present or all null"
            );
        }
        if (allPresent) {
            validateCanonicalCommandId(activeCommandId);
            validateGuardedCommandType(activeCommandType);
        }
    }

    private void validateCanonicalCommandId(String commandId) {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("commandId must not be blank");
        }
        try {
            UUID parsed = UUID.fromString(commandId);
            if (!parsed.toString().equals(commandId)) {
                throw new IllegalArgumentException("commandId must be a canonical UUID");
            }
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "commandId must be a canonical UUID",
                    exception
            );
        }
    }

    private void validateGuardedCommandType(MeetingAnalysisCommandType commandType) {
        switch (commandType) {
            case MEETING_ANALYSIS_REQUESTED,
                 NODE_CONTENT_UPDATE_REQUESTED,
                 NODE_DELETE_REQUESTED -> {
            }
        }
    }
}
