package com.ssafy.projectree.domain.meeting.result.inbox.entity;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
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
        name = "meeting_analysis_result_inbox",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_analysis_result_event_id",
                columnNames = "event_id"
        ),
        indexes = {
                @Index(
                        name = "idx_meeting_analysis_result_command",
                        columnList = "command_id"
                ),
                @Index(
                        name = "idx_meeting_analysis_result_meeting",
                        columnList = "meeting_id, processed_at"
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingAnalysisResultInbox {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_schema_version", nullable = false)
    private int eventSchemaVersion;

    @Column(name = "event_id", nullable = false, length = 36)
    private String eventId;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 50)
    private AnalysisResultEventType eventType;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "meeting_id", nullable = false)
    private int meetingId;

    @Column(name = "command_id", nullable = false, length = 36)
    private String commandId;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "processed_at", nullable = false)
    private Instant processedAt;

    public static MeetingAnalysisResultInbox processed(
            AnalysisResultEventEnvelope event,
            Instant processedAt
    ) {
        Objects.requireNonNull(event, "event must not be null");
        MeetingAnalysisResultInbox inbox = new MeetingAnalysisResultInbox();
        inbox.eventSchemaVersion = event.eventSchemaVersion();
        inbox.eventId = Objects.requireNonNull(event.eventId(), "eventId must not be null");
        inbox.eventType = Objects.requireNonNull(event.eventType(), "eventType must not be null");
        inbox.projectId = requirePositive(event.projectId(), "projectId");
        inbox.meetingId = requirePositive(event.meetingId(), "meetingId");
        inbox.commandId = Objects.requireNonNull(event.commandId(), "commandId must not be null");
        inbox.occurredAt = Objects.requireNonNull(event.occurredAt(), "occurredAt must not be null");
        inbox.processedAt = Objects.requireNonNull(processedAt, "processedAt must not be null");
        return inbox;
    }

    private static int requirePositive(Integer value, String fieldName) {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(fieldName + " must be positive");
        }
        return value;
    }
}
