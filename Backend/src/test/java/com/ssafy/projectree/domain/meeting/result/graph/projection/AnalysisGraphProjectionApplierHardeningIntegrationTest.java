package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
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
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;

@ActiveProfiles("test")
@SpringBootTest
class AnalysisGraphProjectionApplierHardeningIntegrationTest {

    @MockitoBean private GoogleOAuthClient googleOAuthClient;
    @MockitoBean private NaverOAuthClient naverOAuthClient;
    @MockitoSpyBean private NodeEvidenceProjectionRepository evidenceRepository;
    @MockitoSpyBean private MeetingAnalysisNotificationOutboxRepository notificationRepository;

    @Autowired private AnalysisGraphProjectionApplier applier;
    @Autowired private PlatformTransactionManager transactionManager;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        notificationRepository.deleteAll();
        evidenceRepository.deleteAll();
        nodeRepository.deleteAll();
        graphSyncRepository.deleteAll();
        commandRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void replacesManagedProjectionEntitiesWithSameIdsAfterExplicitClear() {
        Fixture fixture = fixture();
        ExistingProjection existing = existingProjection(fixture, 1, "old title", "old content", "old quote");
        saveExistingProjection(fixture, existing);
        ProjectGraphChangedPayload payload = payload(2);

        new TransactionTemplate(transactionManager).executeWithoutResult(status -> {
            assertThat(nodeRepository.findByNodeIdAndProjectId(existing.nodeId(), fixture.projectId())).isPresent();
            applier.apply(event(fixture), payload,
                    snapshot(fixture, 2, existing.nodeId(), existing.evidenceId(), "new title", "new content", "new quote"));
        });

        ProjectNodeProjection replacedNode = nodeRepository.findById(existing.nodeId()).orElseThrow();
        NodeEvidenceProjection replacedEvidence = evidenceRepository.findById(existing.evidenceId()).orElseThrow();
        assertThat(replacedNode.getTitle()).isEqualTo("new title");
        assertThat(replacedNode.getContent()).isEqualTo("new content");
        assertThat(replacedEvidence.getQuoteText()).isEqualTo("new quote");
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow().getCurrentGraphVersion())
                .isEqualTo(2);
    }

    @Test
    void rollsBackEverythingWhenEvidenceInsertFails() {
        Fixture fixture = fixture();
        ExistingProjection existing = existingProjection(fixture, 1, "old title", "old content", "old quote");
        saveExistingProjection(fixture, existing);
        doThrow(new DataIntegrityViolationException("evidence insert failed"))
                .when(evidenceRepository).saveAllAndFlush(any());

        assertThatThrownBy(() -> applier.apply(event(fixture), payload(2),
                snapshot(fixture, 2, existing.nodeId(), existing.evidenceId(), "new title", "new content", "new quote")))
                .isInstanceOf(DataIntegrityViolationException.class);

        assertRollbackState(fixture, existing);
    }

    @Test
    void rollsBackEverythingWhenNotificationInsertFails() {
        Fixture fixture = fixture();
        ExistingProjection existing = existingProjection(fixture, 1, "old title", "old content", "old quote");
        saveExistingProjection(fixture, existing);
        doThrow(new DataIntegrityViolationException("notification insert failed"))
                .when(notificationRepository).saveAndFlush(any());

        assertThatThrownBy(() -> applier.apply(event(fixture), payload(2),
                snapshot(fixture, 2, existing.nodeId(), existing.evidenceId(), "new title", "new content", "new quote")))
                .isInstanceOf(DataIntegrityViolationException.class);

        assertRollbackState(fixture, existing);
    }

    private void assertRollbackState(Fixture fixture, ExistingProjection existing) {
        assertThat(nodeRepository.findById(existing.nodeId()).orElseThrow().getTitle()).isEqualTo("old title");
        assertThat(evidenceRepository.findById(existing.evidenceId()).orElseThrow().getQuoteText()).isEqualTo("old quote");
        assertThat(inboxRepository.count()).isZero();
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow().getCurrentGraphVersion())
                .isEqualTo(1);
        assertThat(notificationRepository.count()).isZero();
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
        return new Fixture(project.getId(), meeting.getId(), command.getCommandId());
    }

    private ExistingProjection existingProjection(
            Fixture fixture,
            long version,
            String title,
            String content,
            String quote
    ) {
        return new ExistingProjection(UUID.randomUUID().toString(), UUID.randomUUID().toString(), version,
                title, content, quote);
    }

    private void saveExistingProjection(Fixture fixture, ExistingProjection existing) {
        Instant now = Instant.parse("2026-08-05T00:00:00Z");
        ProjectGraphSync sync = ProjectGraphSync.initial(fixture.projectId(), now);
        sync.advanceTo(existing.version(), fixture.commandId(), now.plusSeconds(1));
        graphSyncRepository.saveAndFlush(sync);
        ProjectGraphSnapshot snapshot = snapshot(
                fixture, existing.version(), existing.nodeId(), existing.evidenceId(),
                existing.title(), existing.content(), existing.quote()
        );
        nodeRepository.saveAndFlush(ProjectNodeProjection.from(fixture.projectId(), snapshot.nodes().getFirst(), now));
        evidenceRepository.saveAndFlush(NodeEvidenceProjection.from(snapshot.evidences().getFirst(), now));
    }

    private ProjectGraphChangedPayload payload(long version) {
        return new ProjectGraphChangedPayload(
                GraphResultSourceType.MEETING_ANALYSIS, version,
                new GraphSnapshotReference("graph-bucket", "graph-snapshots/test.json", "application/json", 1,
                        "a".repeat(64))
        );
    }

    private AnalysisResultEventEnvelope event(Fixture fixture) {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.parse("2026-08-05T00:00:00Z"), fixture.projectId(), fixture.meetingId(), fixture.commandId(),
                objectMapper.createObjectNode()
        );
    }

    private ProjectGraphSnapshot snapshot(
            Fixture fixture,
            long graphVersion,
            String nodeId,
            String evidenceId,
            String title,
            String content,
            String quote
    ) {
        Instant now = Instant.parse("2026-08-05T00:00:00Z");
        return new ProjectGraphSnapshot(
                1, fixture.projectId(), fixture.meetingId(), fixture.commandId(), graphVersion, now,
                List.of(new ProjectGraphSnapshotNode(nodeId, fixture.meetingId(), null, null,
                        GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                        title, content, null, graphVersion, now, now)),
                List.of(new ProjectGraphSnapshotEvidence(evidenceId, nodeId, fixture.meetingId(), quote,
                        null, null, null, 1)),
                List.of()
        );
    }

    private record Fixture(int projectId, int meetingId, String commandId) {
    }

    private record ExistingProjection(
            String nodeId,
            String evidenceId,
            long version,
            String title,
            String content,
            String quote
    ) {
    }
}
