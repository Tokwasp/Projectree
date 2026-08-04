package com.ssafy.projectree.domain.meeting.entity;

import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
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

import java.util.Objects;

@Entity
@Table(
        name = "meeting",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_room_name",
                columnNames = "room_name"
        )
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Meeting extends BaseEntity {

    private static final int MAX_ROOM_NAME_LENGTH = 128;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(name = "room_name", nullable = false, length = MAX_ROOM_NAME_LENGTH)
    private String roomName;

    @Column(name = "generate_summary", nullable = false)
    private boolean generateSummary;

    @Enumerated(EnumType.STRING)
    @Column(name = "summary_status", nullable = false, length = 30)
    private AnalysisTaskStatus summaryStatus;

    @Column(name = "generate_nodes", nullable = false)
    private boolean generateNodes;

    @Enumerated(EnumType.STRING)
    @Column(name = "node_status", nullable = false, length = 30)
    private AnalysisTaskStatus nodeStatus;

    public static Meeting create(Project project, String roomName) {
        validateRoomName(roomName);

        Meeting meeting = new Meeting();
        meeting.project = Objects.requireNonNull(project, "project must not be null");
        meeting.roomName = roomName;
        meeting.generateSummary = false;
        meeting.summaryStatus = AnalysisTaskStatus.NOT_REQUESTED;
        meeting.generateNodes = false;
        meeting.nodeStatus = AnalysisTaskStatus.NOT_REQUESTED;
        return meeting;
    }

    public boolean isAnalysisRequestConfirmed() {
        return summaryStatus != AnalysisTaskStatus.NOT_REQUESTED
                || nodeStatus != AnalysisTaskStatus.NOT_REQUESTED;
    }

    public void confirmAnalysisOptions(boolean generateSummary, boolean generateNodes) {
        if (isAnalysisRequestConfirmed()) {
            throw new IllegalStateException("analysis request has already been confirmed");
        }

        this.generateSummary = generateSummary;
        this.summaryStatus = requestedStatus(generateSummary);
        this.generateNodes = generateNodes;
        this.nodeStatus = requestedStatus(generateNodes);
    }

    public void markSummarySucceeded() {
        summaryStatus = succeeded(summaryStatus, "summary");
    }

    public void markSummaryFailed() {
        summaryStatus = failed(summaryStatus, "summary");
    }

    public void markNodesSucceeded() {
        nodeStatus = succeeded(nodeStatus, "nodes");
    }

    public void markNodesFailed() {
        nodeStatus = failed(nodeStatus, "nodes");
    }

    private static AnalysisTaskStatus requestedStatus(boolean requested) {
        return requested ? AnalysisTaskStatus.PROCESSING : AnalysisTaskStatus.SKIPPED;
    }

    private static AnalysisTaskStatus succeeded(AnalysisTaskStatus current, String taskName) {
        requireProcessing(current, taskName);
        return AnalysisTaskStatus.SUCCEEDED;
    }

    private static AnalysisTaskStatus failed(AnalysisTaskStatus current, String taskName) {
        requireProcessing(current, taskName);
        return AnalysisTaskStatus.FAILED;
    }

    private static void requireProcessing(AnalysisTaskStatus current, String taskName) {
        if (current != AnalysisTaskStatus.PROCESSING) {
            throw new IllegalStateException(
                    taskName + " task must be PROCESSING but was " + current
            );
        }
    }

    private static void validateRoomName(String roomName) {
        if (roomName == null || roomName.isBlank()) {
            throw new IllegalArgumentException("roomName must not be null or blank");
        }
        if (roomName.length() > MAX_ROOM_NAME_LENGTH) {
            throw new IllegalArgumentException("roomName must be 128 characters or fewer");
        }
    }
}
