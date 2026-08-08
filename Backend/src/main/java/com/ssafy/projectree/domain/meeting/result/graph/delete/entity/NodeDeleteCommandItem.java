package com.ssafy.projectree.domain.meeting.result.graph.delete.entity;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteItemType;
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
        name = "node_delete_command_item",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_node_delete_command_item_command_node",
                columnNames = {"node_delete_command_id", "node_id"}
        ),
        indexes = @Index(
                name = "idx_node_delete_command_item_node",
                columnList = "node_id, node_delete_command_id"
        )
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NodeDeleteCommandItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
            name = "node_delete_command_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_node_delete_command_item_command")
    )
    private NodeDeleteCommand command;

    @Column(name = "node_id", nullable = false, length = 36)
    private String nodeId;

    @Column(name = "expected_node_version", nullable = false)
    private long expectedNodeVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "item_type", nullable = false, length = 20)
    private NodeDeleteItemType itemType;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    public static NodeDeleteCommandItem requested(
            NodeDeleteCommand command,
            String nodeId,
            long expectedNodeVersion,
            LocalDateTime createdAt
    ) {
        return create(
                command,
                nodeId,
                expectedNodeVersion,
                NodeDeleteItemType.REQUESTED,
                createdAt
        );
    }

    public static NodeDeleteCommandItem mergedSource(
            NodeDeleteCommand command,
            String nodeId,
            long expectedNodeVersion,
            LocalDateTime createdAt
    ) {
        return create(
                command,
                nodeId,
                expectedNodeVersion,
                NodeDeleteItemType.MERGED_SOURCE,
                createdAt
        );
    }

    private static NodeDeleteCommandItem create(
            NodeDeleteCommand command,
            String nodeId,
            long expectedNodeVersion,
            NodeDeleteItemType itemType,
            LocalDateTime createdAt
    ) {
        if (expectedNodeVersion < 0) {
            throw new IllegalArgumentException("expectedNodeVersion must not be negative");
        }
        NodeDeleteCommandItem item = new NodeDeleteCommandItem();
        item.command = Objects.requireNonNull(command, "command must not be null");
        item.nodeId = canonicalUuid(nodeId);
        item.expectedNodeVersion = expectedNodeVersion;
        item.itemType = Objects.requireNonNull(itemType, "itemType must not be null");
        item.createdAt = Objects.requireNonNull(createdAt, "createdAt must not be null");
        return item;
    }

    private static String canonicalUuid(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("nodeId must not be null or blank");
        }
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equals(value)) {
                throw new IllegalArgumentException("nodeId must be a canonical UUID");
            }
            return value;
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("nodeId must be a canonical UUID", exception);
        }
    }
}
