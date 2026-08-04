package com.ssafy.projectree.domain.meeting.outbox.entity;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(
        name = "meeting_analysis_command_outbox",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_meeting_analysis_command_outbox_command_id",
                        columnNames = "command_id"
                ),
                @UniqueConstraint(
                        name = "uk_meeting_analysis_command_outbox_meeting_type",
                        columnNames = {"meeting_id", "command_type"}
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingAnalysisCommandOutbox extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @Column(name = "command_id", nullable = false, length = 36)
    private String commandId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
            name = "meeting_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_meeting_analysis_command_outbox_meeting")
    )
    private Meeting meeting;

    @Enumerated(EnumType.STRING)
    @Column(name = "command_type", nullable = false, length = 64)
    private MeetingAnalysisCommandType commandType;

    @Column(nullable = false, columnDefinition = "LONGTEXT")
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private MeetingAnalysisOutboxStatus status;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @Column(name = "published_at")
    private LocalDateTime publishedAt;

    @Column(name = "last_error", length = 1000)
    private String lastError;

    public static MeetingAnalysisCommandOutbox pending(
            UUID commandId,
            Meeting meeting,
            MeetingAnalysisCommandType commandType,
            String payload
    ) {
        MeetingAnalysisCommandOutbox outbox = new MeetingAnalysisCommandOutbox();
        outbox.commandId = Objects.requireNonNull(commandId, "commandId must not be null").toString();
        outbox.meeting = Objects.requireNonNull(meeting, "meeting must not be null");
        outbox.commandType = Objects.requireNonNull(commandType, "commandType must not be null");
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload must not be null or blank");
        }
        outbox.payload = payload;
        outbox.status = MeetingAnalysisOutboxStatus.PENDING;
        outbox.attemptCount = 0;
        return outbox;
    }
}
