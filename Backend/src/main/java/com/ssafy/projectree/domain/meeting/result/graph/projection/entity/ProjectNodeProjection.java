package com.ssafy.projectree.domain.meeting.result.graph.projection.entity;

import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
        name = "project_node_projection",
        indexes = {
                @Index(name = "idx_project_node_tree", columnList = "project_id, graph_state, category"),
                @Index(name = "idx_project_node_parent", columnList = "project_id, parent_node_id"),
                @Index(name = "idx_project_node_merged_target", columnList = "project_id, merged_into_node_id"),
                @Index(name = "idx_project_node_source_meeting", columnList = "source_meeting_id")
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ProjectNodeProjection {

    @Id
    @Column(name = "node_id", nullable = false, length = 36)
    private String nodeId;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "source_meeting_id")
    private Integer sourceMeetingId;

    @Column(name = "parent_node_id", length = 36)
    private String parentNodeId;

    @Column(name = "merged_into_node_id", length = 36)
    private String mergedIntoNodeId;

    @Enumerated(EnumType.STRING)
    @Column(name = "node_type", nullable = false, length = 20)
    private GraphNodeType nodeType;

    @Enumerated(EnumType.STRING)
    @Column(name = "category", nullable = false, length = 20)
    private GraphNodeCategory category;

    @Enumerated(EnumType.STRING)
    @Column(name = "graph_state", nullable = false, length = 20)
    private GraphNodeState graphState;

    @Column(name = "title", nullable = false, length = 255)
    private String title;

    @Column(name = "content", nullable = false, columnDefinition = "MEDIUMTEXT")
    private String content;

    @Enumerated(EnumType.STRING)
    @Column(name = "link_source", length = 20)
    private GraphLinkSource linkSource;

    @Column(name = "source_node_version", nullable = false)
    private long sourceNodeVersion;

    @Column(name = "source_created_at", nullable = false)
    private Instant sourceCreatedAt;

    @Column(name = "source_updated_at", nullable = false)
    private Instant sourceUpdatedAt;

    @Column(name = "synced_at", nullable = false)
    private Instant syncedAt;

    public static ProjectNodeProjection from(int projectId, ProjectGraphSnapshotNode node, Instant syncedAt) {
        if (projectId <= 0) {
            throw new IllegalArgumentException("projectId must be positive");
        }
        Objects.requireNonNull(node, "node must not be null");
        ProjectNodeProjection projection = new ProjectNodeProjection();
        projection.nodeId = Objects.requireNonNull(node.nodeId(), "nodeId must not be null");
        projection.projectId = projectId;
        projection.sourceMeetingId = node.sourceMeetingId();
        projection.parentNodeId = node.parentNodeId();
        projection.mergedIntoNodeId = node.mergedIntoNodeId();
        projection.nodeType = Objects.requireNonNull(node.nodeType(), "nodeType must not be null");
        projection.category = Objects.requireNonNull(node.category(), "category must not be null");
        projection.graphState = Objects.requireNonNull(node.graphState(), "graphState must not be null");
        projection.title = Objects.requireNonNull(node.title(), "title must not be null");
        projection.content = Objects.requireNonNull(node.content(), "content must not be null");
        projection.linkSource = node.linkSource();
        projection.sourceNodeVersion = node.nodeVersion();
        projection.sourceCreatedAt = Objects.requireNonNull(node.createdAt(), "createdAt must not be null");
        projection.sourceUpdatedAt = Objects.requireNonNull(node.updatedAt(), "updatedAt must not be null");
        projection.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
        return projection;
    }
}
