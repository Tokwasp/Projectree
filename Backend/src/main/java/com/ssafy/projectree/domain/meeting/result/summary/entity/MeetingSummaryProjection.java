package com.ssafy.projectree.domain.meeting.result.summary.entity;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryReadyPayload;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryResultStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
        name = "meeting_summary_projection",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_summary_projection_meeting",
                columnNames = "meeting_id"
        ),
        indexes = {
                @Index(
                        name = "idx_meeting_summary_projection_project",
                        columnList = "project_id, synced_at"
                ),
                @Index(
                        name = "idx_meeting_summary_projection_command",
                        columnList = "command_id"
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingSummaryProjection {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private int meetingId;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "command_id", nullable = false, length = 36)
    private String commandId;

    @Column(name = "meeting_summary_id", nullable = false, length = 36)
    private String meetingSummaryId;

    @Column(name = "summary_version", nullable = false)
    private int summaryVersion;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MeetingSummaryResultStatus status;

    @Column(name = "api_path", nullable = false, length = 500)
    private String apiPath;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "synced_at", nullable = false)
    private Instant syncedAt;

    public static MeetingSummaryProjection create(
            int meetingId,
            int projectId,
            String commandId,
            MeetingSummaryReadyPayload payload,
            Instant occurredAt,
            Instant syncedAt
    ) {
        MeetingSummaryProjection projection = new MeetingSummaryProjection();
        projection.meetingId = requirePositive(meetingId, "meetingId");
        projection.projectId = requirePositive(projectId, "projectId");
        projection.commandId = requireText(commandId, "commandId");
        projection.meetingSummaryId = requireText(payload.meetingSummaryId(), "meetingSummaryId");
        projection.summaryVersion = requirePositive(payload.summaryVersion(), "summaryVersion");
        projection.status = Objects.requireNonNull(payload.status(), "status must not be null");
        projection.apiPath = requireText(payload.apiPath(), "apiPath");
        projection.occurredAt = Objects.requireNonNull(occurredAt, "occurredAt must not be null");
        projection.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
        return projection;
    }

    public boolean applyIfNewer(
            String incomingCommandId,
            MeetingSummaryReadyPayload payload,
            Instant incomingOccurredAt,
            Instant incomingSyncedAt
    ) {
        if (payload.summaryVersion() < summaryVersion) {
            return false;
        }
        if (payload.summaryVersion() == summaryVersion) {
            if (hasSameCoreValues(incomingCommandId, payload)) {
                return false;
            }
            throw new AnalysisResultContractException("Conflicting meeting summary payload for same version");
        }
        commandId = requireText(incomingCommandId, "commandId");
        meetingSummaryId = requireText(payload.meetingSummaryId(), "meetingSummaryId");
        summaryVersion = payload.summaryVersion();
        status = Objects.requireNonNull(payload.status(), "status must not be null");
        apiPath = requireText(payload.apiPath(), "apiPath");
        occurredAt = Objects.requireNonNull(incomingOccurredAt, "occurredAt must not be null");
        syncedAt = Objects.requireNonNull(incomingSyncedAt, "syncedAt must not be null");
        return true;
    }

    private boolean hasSameCoreValues(String incomingCommandId, MeetingSummaryReadyPayload payload) {
        return meetingSummaryId.equals(payload.meetingSummaryId())
                && commandId.equals(incomingCommandId)
                && status == payload.status()
                && apiPath.equals(payload.apiPath());
    }

    private static int requirePositive(int value, String fieldName) {
        if (value <= 0) {
            throw new IllegalArgumentException(fieldName + " must be positive");
        }
        return value;
    }

    private static String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return value;
    }
}
