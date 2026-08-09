package com.ssafy.projectree.domain.meeting.result.graph.projection.entity;

import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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
        name = "node_evidence_projection",
        indexes = {
                @Index(name = "idx_node_evidence_order", columnList = "node_id, evidence_order"),
                @Index(name = "idx_node_evidence_meeting", columnList = "meeting_id")
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NodeEvidenceProjection {

    @Id
    @Column(name = "evidence_id", nullable = false, length = 36)
    private String evidenceId;

    @Column(name = "node_id", nullable = false, length = 36)
    private String nodeId;

    @Column(name = "meeting_id", nullable = false)
    private int meetingId;

    @Column(name = "quote_text", nullable = false, columnDefinition = "TEXT")
    private String quoteText;

    @Column(name = "speaker_label", length = 100)
    private String speakerLabel;

    @Column(name = "start_ms")
    private Long startMs;

    @Column(name = "end_ms")
    private Long endMs;

    @Column(name = "evidence_order", nullable = false)
    private int evidenceOrder;

    @Column(name = "synced_at", nullable = false)
    private Instant syncedAt;

    public static NodeEvidenceProjection from(ProjectGraphSnapshotEvidence evidence, Instant syncedAt) {
        Objects.requireNonNull(evidence, "evidence must not be null");
        NodeEvidenceProjection projection = new NodeEvidenceProjection();
        projection.evidenceId = Objects.requireNonNull(evidence.evidenceId(), "evidenceId must not be null");
        projection.nodeId = Objects.requireNonNull(evidence.nodeId(), "nodeId must not be null");
        projection.meetingId = evidence.meetingId();
        projection.quoteText = Objects.requireNonNull(evidence.quoteText(), "quoteText must not be null");
        projection.speakerLabel = evidence.speakerLabel();
        projection.startMs = evidence.startMs();
        projection.endMs = evidence.endMs();
        projection.evidenceOrder = evidence.evidenceOrder();
        projection.syncedAt = Objects.requireNonNull(syncedAt, "syncedAt must not be null");
        return projection;
    }
}
