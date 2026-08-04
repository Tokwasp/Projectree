package com.ssafy.projectree.domain.meeting.entity;

import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
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

import java.util.Objects;

@Entity
@Table(
        name = "meeting",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_room_name",
                columnNames = "room_name"
        ),
        indexes = @Index(
                name = "idx_meeting_project_creator",
                columnList = "project_id, creator_member_id"
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

    @Column(name = "creator_member_id")
    private Integer creatorMemberId;

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

    public static Meeting create(
            Project project,
            ProjectMember creatorProjectMember,
            String roomName
    ) {
        validateRoomName(roomName);

        Meeting meeting = new Meeting();
        meeting.project = Objects.requireNonNull(project, "project must not be null");
        meeting.registerCreator(creatorProjectMember);
        meeting.roomName = roomName;
        meeting.generateSummary = false;
        meeting.summaryStatus = AnalysisTaskStatus.NOT_REQUESTED;
        meeting.generateNodes = false;
        meeting.nodeStatus = AnalysisTaskStatus.NOT_REQUESTED;
        return meeting;
    }

    public boolean registerCreator(ProjectMember creatorProjectMember) {
        Objects.requireNonNull(creatorProjectMember, "creatorProjectMember must not be null");
        if (project == null || !creatorProjectMember.belongsTo(project)) {
            throw new IllegalArgumentException("creatorProjectMember must belong to meeting project");
        }
        if (this.creatorMemberId == null) {
            this.creatorMemberId = creatorProjectMember.getMemberId();
            return true;
        }
        if (isCreatedBy(creatorProjectMember)) {
            return false;
        }
        throw new IllegalStateException("meeting creator is already registered");
    }

    public boolean isCreatedBy(ProjectMember projectMember) {
        return creatorMemberId != null
                && projectMember != null
                && creatorMemberId == projectMember.getMemberId();
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

    public boolean failSummaryAnalysis() {
        if (summaryStatus == AnalysisTaskStatus.PROCESSING) {
            summaryStatus = AnalysisTaskStatus.FAILED;
            return true;
        }
        return isFailureNoOpAllowed(summaryStatus, "summary");
    }

    public boolean failNodeAnalysis() {
        if (nodeStatus == AnalysisTaskStatus.PROCESSING) {
            nodeStatus = AnalysisTaskStatus.FAILED;
            return true;
        }
        return isFailureNoOpAllowed(nodeStatus, "nodes");
    }

    public AnalysisTaskCompletionResult completeSummaryAnalysis() {
        return switch (summaryStatus) {
            case PROCESSING -> {
                summaryStatus = AnalysisTaskStatus.SUCCEEDED;
                yield AnalysisTaskCompletionResult.APPLIED;
            }
            case SUCCEEDED -> AnalysisTaskCompletionResult.ALREADY_SUCCEEDED;
            case FAILED -> AnalysisTaskCompletionResult.ALREADY_FAILED;
            case SKIPPED, NOT_REQUESTED -> throw new IllegalStateException(
                    "summary task cannot receive a success event while " + summaryStatus
            );
        };
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

    private static boolean isFailureNoOpAllowed(AnalysisTaskStatus current, String taskName) {
        if (current == AnalysisTaskStatus.FAILED || current == AnalysisTaskStatus.SUCCEEDED) {
            return false;
        }
        throw new IllegalStateException(
                taskName + " task cannot receive a failure event while " + current
        );
    }

    private static void validateRoomName(String roomName) {
        if (roomName == null || roomName.isBlank()) {
            throw new IllegalArgumentException("roomName must not be null or blank");
        }
        if (roomName.length() > MAX_ROOM_NAME_LENGTH) {
            throw new IllegalArgumentException("roomName must be 128 characters or fewer");
        }
        try {
            java.util.UUID parsed = java.util.UUID.fromString(roomName);
            if (!parsed.toString().equalsIgnoreCase(roomName)) {
                throw new IllegalArgumentException("roomName must be a canonical UUID");
            }
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("roomName must be a canonical UUID", exception);
        }
    }
}
