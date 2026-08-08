package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationType;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.aop.support.AopUtils;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class AnalysisGraphProjectionApplierIntegrationTest extends IntegrationTestSupport {

    @Autowired private AnalysisGraphProjectionApplier applier;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;
    @Autowired private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired private ObjectMapper objectMapper;

    @Test
    void processingNodeResultAtomicallyCompletesAndReplacesProjection() throws Exception {
        Fixture fixture = fixture();
        ProjectGraphChangedPayload payload = payload(3);
        GraphProjectionApplyResult result = applier.apply(
                event(fixture, payload), payload, snapshot(fixture, payload.graphVersion())
        );

        assertThat(AopUtils.isAopProxy(applier)).isTrue();
        assertThat(result.completionResult()).isEqualTo(AnalysisTaskCompletionResult.APPLIED);
        assertThat(result.projectionUpdated()).isTrue();
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.SKIPPED);
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isEqualTo(1);
        assertThat(evidenceRepository.count()).isEqualTo(1);
        ProjectGraphSync sync = graphSyncRepository.findById(fixture.projectId()).orElseThrow();
        assertThat(sync.getCurrentGraphVersion()).isEqualTo(3);
        assertThat(sync.getLastCommandId()).isEqualTo(fixture.commandId());
        assertThat(sync.hasActiveCommand()).isFalse();
        MeetingAnalysisNotificationOutbox notification = notificationRepository.findAll().getFirst();
        assertThat(notification.getRecipientMemberId()).isEqualTo(17);
        assertThat(notification.getNotificationType()).isEqualTo(NotificationType.MEETING_NODE_ANALYSIS_SUCCEEDED);
        JsonNode notificationPayload = objectMapper.readTree(notification.getPayload());
        assertThat(notificationPayload.get("requestedGraphVersion").asLong()).isEqualTo(3);
        assertThat(notificationPayload.get("currentGraphVersion").asLong()).isEqualTo(3);
        assertThat(notificationPayload.get("projectionUpdated").asBoolean()).isTrue();
    }

    @Test
    void staleGraphStillCompletesProcessingNodeButDoesNotReplaceProjection() {
        Fixture fixture = fixture();
        ProjectGraphSync sync = graphSyncRepository.findById(fixture.projectId())
                .orElseThrow();
        sync.advanceTo(5, UUID.randomUUID().toString(), Instant.parse("2026-08-05T00:00:01Z"));
        graphSyncRepository.saveAndFlush(sync);
        ProjectGraphChangedPayload payload = payload(4);

        GraphProjectionApplyResult result = applier.apply(
                event(fixture, payload), payload, snapshot(fixture, payload.graphVersion())
        );

        assertThat(result.completionResult()).isEqualTo(AnalysisTaskCompletionResult.APPLIED);
        assertThat(result.projectionUpdated()).isFalse();
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow().getCurrentGraphVersion())
                .isEqualTo(5);
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isZero();
        assertThat(notificationRepository.count()).isEqualTo(1);
    }

    @Test
    void failedNodeKeepsFinalStateAndOnlyRegistersInbox() {
        Fixture fixture = fixture();
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        meeting.markNodesFailed();
        meetingRepository.saveAndFlush(meeting);
        ProjectGraphChangedPayload payload = payload(2);

        GraphProjectionApplyResult result = applier.apply(
                event(fixture, payload), payload, snapshot(fixture, payload.graphVersion())
        );

        assertThat(result.completionResult()).isEqualTo(AnalysisTaskCompletionResult.ALREADY_FAILED);
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isZero();
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow().getCurrentGraphVersion())
                .isZero();
        assertThat(notificationRepository.count()).isZero();
        assertThat(inboxRepository.count()).isEqualTo(1);
    }

    private Fixture fixture() {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
        meeting.confirmAnalysisOptions(false, true);
        meeting = meetingRepository.saveAndFlush(meeting);
        MeetingAnalysisCommandOutbox command = commandRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        UUID.randomUUID(), meeting, MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{\"command\":true}", 17, LocalDateTime.now()
                )
        );
        ProjectGraphSync sync = ProjectGraphSync.initial(
                project.getId(),
                Instant.parse("2026-08-05T00:00:00Z")
        );
        sync.acquireGraphOperation(
                command.getCommandId(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.parse("2026-08-05T00:00:01Z")
        );
        graphSyncRepository.saveAndFlush(sync);
        return new Fixture(project.getId(), meeting.getId(), command.getCommandId());
    }

    private ProjectGraphChangedPayload payload(long version) {
        return new ProjectGraphChangedPayload(
                GraphResultSourceType.MEETING_ANALYSIS,
                version,
                new GraphSnapshotReference("graph-bucket", "graph-snapshots/test.json", "application/json", 1,
                        "a".repeat(64))
        );
    }

    private AnalysisResultEventEnvelope event(Fixture fixture, ProjectGraphChangedPayload payload) {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.parse("2026-08-05T00:00:00Z"), fixture.projectId(), fixture.meetingId(), fixture.commandId(),
                objectMapper.createObjectNode().put("graphVersion", payload.graphVersion())
        );
    }

    private ProjectGraphSnapshot snapshot(Fixture fixture, long graphVersion) {
        Instant now = Instant.parse("2026-08-05T00:00:00Z");
        String nodeId = UUID.randomUUID().toString();
        return new ProjectGraphSnapshot(
                1, fixture.projectId(), fixture.meetingId(), fixture.commandId(), graphVersion, now,
                List.of(new ProjectGraphSnapshotNode(nodeId, fixture.meetingId(), null, null,
                        GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                        "title", "content", null, 1, now, now)),
                List.of(new ProjectGraphSnapshotEvidence(UUID.randomUUID().toString(), nodeId, fixture.meetingId(),
                        "quote", null, null, null, 1)),
                List.of()
        );
    }

    private record Fixture(int projectId, int meetingId, String commandId) {
    }
}
