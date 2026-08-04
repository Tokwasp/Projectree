package com.ssafy.projectree.domain.meeting.notification.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.Objects;
import java.util.UUID;

@Entity
@Table(
        name = "meeting_analysis_notification_outbox",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_meeting_analysis_notification_id",
                        columnNames = "notification_id"
                ),
                @UniqueConstraint(
                        name = "uk_meeting_analysis_notification_command_audience_type",
                        columnNames = {"command_id", "audience", "notification_type"}
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingAnalysisNotificationOutbox extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @Column(name = "notification_id", nullable = false, length = 36)
    private String notificationId;

    @Column(name = "command_id", nullable = false, length = 36)
    private String commandId;

    @Column(name = "meeting_id", nullable = false)
    private int meetingId;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "recipient_member_id")
    private Integer recipientMemberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private NotificationAudience audience;

    @Enumerated(EnumType.STRING)
    @Column(name = "notification_type", nullable = false, length = 64)
    private NotificationType notificationType;

    @Column(nullable = false, columnDefinition = "LONGTEXT")
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private NotificationOutboxStatus status;

    public static MeetingAnalysisNotificationOutbox pending(
            String commandId,
            int meetingId,
            int projectId,
            Integer recipientMemberId,
            NotificationAudience audience,
            String payload
    ) {
        MeetingAnalysisNotificationOutbox outbox = new MeetingAnalysisNotificationOutbox();
        outbox.notificationId = UUID.randomUUID().toString();
        outbox.commandId = requireText(commandId, "commandId");
        outbox.meetingId = requirePositive(meetingId, "meetingId");
        outbox.projectId = requirePositive(projectId, "projectId");
        outbox.audience = Objects.requireNonNull(audience, "audience must not be null");
        if (audience == NotificationAudience.USER && recipientMemberId == null) {
            throw new IllegalArgumentException("USER notification requires recipientMemberId");
        }
        if (audience == NotificationAudience.OPERATIONS && recipientMemberId != null) {
            throw new IllegalArgumentException("OPERATIONS notification must not have recipientMemberId");
        }
        outbox.recipientMemberId = recipientMemberId;
        outbox.notificationType = NotificationType.MEETING_ANALYSIS_COMMAND_PUBLISH_FAILED;
        outbox.payload = requireText(payload, "payload");
        outbox.status = NotificationOutboxStatus.PENDING;
        return outbox;
    }

    private static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }

    private static int requirePositive(int value, String name) {
        if (value <= 0) {
            throw new IllegalArgumentException(name + " must be positive");
        }
        return value;
    }
}
