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
import jakarta.persistence.Index;
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
        },
        indexes = {
                @Index(
                        name = "idx_meeting_analysis_outbox_pending",
                        columnList = "status, next_attempt_at, created_at, id"
                ),
                @Index(
                        name = "idx_meeting_analysis_outbox_expired_lease",
                        columnList = "status, lease_until, created_at, id"
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

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
            name = "meeting_id",
            nullable = true,
            foreignKey = @ForeignKey(name = "fk_meeting_analysis_command_outbox_meeting")
    )
    private Meeting meeting;

    @Column(name = "target_project_id")
    private Integer targetProjectId;

    @Column(name = "target_node_id", length = 36)
    private String targetNodeId;

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

    @Column(name = "requested_by_member_id", nullable = false)
    private int requestedByMemberId;

    @Column(name = "next_attempt_at")
    private LocalDateTime nextAttemptAt;

    @Column(name = "lease_until")
    private LocalDateTime leaseUntil;

    @Column(name = "claim_token", length = 36)
    private String claimToken;

    @Column(name = "published_at")
    private LocalDateTime publishedAt;

    @Column(name = "last_error", length = 1000)
    private String lastError;

    public static MeetingAnalysisCommandOutbox pending(
            UUID commandId,
            Meeting meeting,
            MeetingAnalysisCommandType commandType,
            String payload,
            int requestedByMemberId,
            LocalDateTime now
    ) {
        if (commandType != MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED) {
            throw new IllegalArgumentException(
                    "commandType must be MEETING_ANALYSIS_REQUESTED"
            );
        }
        MeetingAnalysisCommandOutbox outbox = new MeetingAnalysisCommandOutbox();
        outbox.commandId = Objects.requireNonNull(commandId, "commandId must not be null").toString();
        outbox.meeting = Objects.requireNonNull(meeting, "meeting must not be null");
        outbox.commandType = commandType;
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload must not be null or blank");
        }
        outbox.payload = payload;
        outbox.status = MeetingAnalysisOutboxStatus.PENDING;
        outbox.attemptCount = 0;
        if (requestedByMemberId <= 0) {
            throw new IllegalArgumentException("requestedByMemberId must be positive");
        }
        outbox.requestedByMemberId = requestedByMemberId;
        outbox.nextAttemptAt = Objects.requireNonNull(now, "now must not be null");
        return outbox;
    }

    public static MeetingAnalysisCommandOutbox pendingNodeContentUpdate(
            UUID commandId,
            int projectId,
            String nodeId,
            MeetingAnalysisCommandType commandType,
            String payload,
            int requestedByMemberId,
            LocalDateTime now
    ) {
        if (projectId <= 0) {
            throw new IllegalArgumentException("projectId must be positive");
        }
        if (nodeId == null || nodeId.isBlank()) {
            throw new IllegalArgumentException("nodeId must not be null or blank");
        }
        if (commandType != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED) {
            throw new IllegalArgumentException("commandType must be NODE_CONTENT_UPDATE_REQUESTED");
        }
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload must not be null or blank");
        }
        if (requestedByMemberId <= 0) {
            throw new IllegalArgumentException("requestedByMemberId must be positive");
        }

        MeetingAnalysisCommandOutbox outbox = new MeetingAnalysisCommandOutbox();
        outbox.commandId = Objects.requireNonNull(commandId, "commandId must not be null").toString();
        outbox.meeting = null;
        outbox.targetProjectId = projectId;
        outbox.targetNodeId = nodeId;
        outbox.commandType = commandType;
        outbox.payload = payload;
        outbox.status = MeetingAnalysisOutboxStatus.PENDING;
        outbox.attemptCount = 0;
        outbox.requestedByMemberId = requestedByMemberId;
        outbox.nextAttemptAt = Objects.requireNonNull(now, "now must not be null");
        return outbox;
    }

    public String claim(LocalDateTime now, LocalDateTime leaseUntil, int maxAttempts) {
        Objects.requireNonNull(now, "now must not be null");
        Objects.requireNonNull(leaseUntil, "leaseUntil must not be null");
        boolean pending = status == MeetingAnalysisOutboxStatus.PENDING
                && nextAttemptAt != null
                && !nextAttemptAt.isAfter(now)
                && attemptCount < maxAttempts;
        boolean expiredLease = status == MeetingAnalysisOutboxStatus.PUBLISHING
                && this.leaseUntil != null
                && !this.leaseUntil.isAfter(now);
        if (!pending && !expiredLease) {
            throw new IllegalStateException("outbox is not claimable");
        }
        if (pending) {
            attemptCount++;
        }
        status = MeetingAnalysisOutboxStatus.PUBLISHING;
        claimToken = UUID.randomUUID().toString();
        this.leaseUntil = leaseUntil;
        nextAttemptAt = null;
        return claimToken;
    }

    public boolean markPublished(String expectedClaimToken, LocalDateTime now) {
        if (!isOwnedBy(expectedClaimToken)) {
            return false;
        }
        status = MeetingAnalysisOutboxStatus.PUBLISHED;
        publishedAt = Objects.requireNonNull(now, "now must not be null");
        clearClaim();
        lastError = null;
        return true;
    }

    public boolean rescheduleOrFail(
            String expectedClaimToken,
            LocalDateTime now,
            int maxAttempts,
            long firstRetryDelaySeconds,
            long secondRetryDelaySeconds,
            String error
    ) {
        if (!isOwnedBy(expectedClaimToken)) {
            return false;
        }
        lastError = truncate(error);
        if (attemptCount >= maxAttempts) {
            status = MeetingAnalysisOutboxStatus.FAILED;
            clearClaim();
            return true;
        }
        long retryDelay = attemptCount == 1
                ? firstRetryDelaySeconds
                : secondRetryDelaySeconds;
        status = MeetingAnalysisOutboxStatus.PENDING;
        nextAttemptAt = Objects.requireNonNull(now, "now must not be null")
                .plusSeconds(retryDelay);
        leaseUntil = null;
        claimToken = null;
        return false;
    }

    public boolean isOwnedBy(String expectedClaimToken) {
        return status == MeetingAnalysisOutboxStatus.PUBLISHING
                && expectedClaimToken != null
                && expectedClaimToken.equals(claimToken);
    }

    private void clearClaim() {
        nextAttemptAt = null;
        leaseUntil = null;
        claimToken = null;
    }

    private static String truncate(String error) {
        String safe = error == null || error.isBlank() ? "Unknown publish failure" : error;
        return safe.length() <= 1000 ? safe : safe.substring(0, 1000);
    }
}
