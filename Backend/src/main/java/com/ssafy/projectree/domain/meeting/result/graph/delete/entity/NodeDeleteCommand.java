package com.ssafy.projectree.domain.meeting.result.graph.delete.entity;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(
        name = "node_delete_command",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_node_delete_command_command_id",
                        columnNames = "command_id"
                ),
                @UniqueConstraint(
                        name = "uk_node_delete_command_outbox_id",
                        columnNames = "outbox_id"
                ),
                @UniqueConstraint(
                        name = "uk_node_delete_command_result_event_id",
                        columnNames = "result_event_id"
                )
        },
        indexes = {
                @Index(
                        name = "idx_node_delete_command_project_status",
                        columnList = "project_id, status"
                ),
                @Index(
                        name = "idx_node_delete_command_status_requested_at",
                        columnList = "status, requested_at"
                )
        }
)
@EntityListeners(AuditingEntityListener.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NodeDeleteCommand {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "command_id", nullable = false, length = 36)
    private String commandId;

    @Column(name = "outbox_id")
    private Integer outboxId;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "expected_graph_version", nullable = false)
    private long expectedGraphVersion;

    @Column(name = "requested_by_member_id", nullable = false)
    private int requestedByMemberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private NodeDeleteCommandStatus status;

    @Column(name = "reason_code", length = 50)
    private String reasonCode;

    @Column(name = "result_event_id", length = 36)
    private String resultEventId;

    @Column(name = "result_graph_version")
    private Long resultGraphVersion;

    @Column(name = "requested_node_count", nullable = false)
    private int requestedNodeCount;

    @Column(name = "merged_source_count", nullable = false)
    private int mergedSourceCount;

    @Column(name = "total_node_count", nullable = false)
    private int totalNodeCount;

    @Column(name = "requested_at", nullable = false)
    private LocalDateTime requestedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Version
    @Column(nullable = false)
    private long version;

    public static NodeDeleteCommand pending(
            UUID commandId,
            int projectId,
            long expectedGraphVersion,
            int requestedByMemberId,
            int requestedNodeCount,
            int mergedSourceCount,
            LocalDateTime requestedAt
    ) {
        if (projectId <= 0) {
            throw new IllegalArgumentException("projectId must be positive");
        }
        if (expectedGraphVersion < 0) {
            throw new IllegalArgumentException("expectedGraphVersion must not be negative");
        }
        if (requestedByMemberId <= 0) {
            throw new IllegalArgumentException("requestedByMemberId must be positive");
        }
        if (requestedNodeCount <= 0) {
            throw new IllegalArgumentException("requestedNodeCount must be positive");
        }
        if (mergedSourceCount < 0) {
            throw new IllegalArgumentException("mergedSourceCount must not be negative");
        }

        NodeDeleteCommand command = new NodeDeleteCommand();
        command.commandId = Objects.requireNonNull(commandId, "commandId must not be null").toString();
        command.projectId = projectId;
        command.expectedGraphVersion = expectedGraphVersion;
        command.requestedByMemberId = requestedByMemberId;
        command.status = NodeDeleteCommandStatus.PENDING;
        command.requestedNodeCount = requestedNodeCount;
        command.mergedSourceCount = mergedSourceCount;
        command.totalNodeCount = Math.addExact(requestedNodeCount, mergedSourceCount);
        command.requestedAt = Objects.requireNonNull(requestedAt, "requestedAt must not be null");
        return command;
    }

    public void markSucceeded(
            UUID resultEventId,
            long resultGraphVersion,
            LocalDateTime completedAt
    ) {
        requirePending();
        if (resultGraphVersion < 0) {
            throw new IllegalArgumentException("resultGraphVersion must not be negative");
        }
        String validatedResultEventId = Objects.requireNonNull(
                resultEventId,
                "resultEventId must not be null"
        ).toString();
        LocalDateTime validatedCompletedAt =
                Objects.requireNonNull(completedAt, "completedAt must not be null");
        this.status = NodeDeleteCommandStatus.SUCCEEDED;
        this.resultEventId = validatedResultEventId;
        this.resultGraphVersion = resultGraphVersion;
        this.completedAt = validatedCompletedAt;
    }

    public void markRejected(
            UUID resultEventId,
            String reasonCode,
            LocalDateTime completedAt
    ) {
        requirePending();
        String validatedResultEventId = Objects.requireNonNull(
                resultEventId,
                "resultEventId must not be null"
        ).toString();
        String validatedReasonCode = requireReasonCode(reasonCode);
        LocalDateTime validatedCompletedAt =
                Objects.requireNonNull(completedAt, "completedAt must not be null");
        this.status = NodeDeleteCommandStatus.REJECTED;
        this.resultEventId = validatedResultEventId;
        this.reasonCode = validatedReasonCode;
        this.completedAt = validatedCompletedAt;
    }

    public void markFailed(String reasonCode, LocalDateTime completedAt) {
        requirePending();
        String validatedReasonCode = requireReasonCode(reasonCode);
        LocalDateTime validatedCompletedAt =
                Objects.requireNonNull(completedAt, "completedAt must not be null");
        this.status = NodeDeleteCommandStatus.FAILED;
        this.reasonCode = validatedReasonCode;
        this.completedAt = validatedCompletedAt;
    }

    public void attachOutbox(int outboxId) {
        if (outboxId <= 0) {
            throw new IllegalArgumentException("outboxId must be positive");
        }
        if (this.outboxId != null) {
            throw new IllegalStateException("outbox is already attached");
        }
        this.outboxId = outboxId;
    }

    private void requirePending() {
        if (status != NodeDeleteCommandStatus.PENDING) {
            throw new IllegalStateException("only a pending command can be completed");
        }
    }

    private static String requireReasonCode(String reasonCode) {
        if (reasonCode == null || reasonCode.isBlank()) {
            throw new IllegalArgumentException("reasonCode must not be null or blank");
        }
        if (reasonCode.length() > 50) {
            throw new IllegalArgumentException("reasonCode must be 50 characters or fewer");
        }
        return reasonCode;
    }
}
