package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.lenient;

@ExtendWith(MockitoExtension.class)
class NodeContentUpdateGraphProjectionApplierTest {

    private static final Instant NOW = Instant.parse("2026-08-06T06:30:02Z");

    @Mock private ProjectRepository projectRepository;
    @Mock private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Mock private ProjectGraphSyncRepository syncRepository;
    @Mock private ResultInboxService inboxService;
    @Mock private GraphProjectionReplacer projectionReplacer;
    @Mock private EntityManager entityManager;
    @Mock private ProjectGraphOperationGuard graphOperationGuard;

    private final ObjectMapper objectMapper = JsonMapper.builder().build();
    private NodeContentUpdateGraphProjectionApplier applier;

    @BeforeEach
    void setUp() {
        applier = new NodeContentUpdateGraphProjectionApplier(
                projectRepository,
                commandRepository,
                syncRepository,
                inboxService,
                projectionReplacer,
                entityManager,
                objectMapper,
                Clock.fixed(NOW, ZoneOffset.UTC),
                graphOperationGuard
        );
        lenient().when(graphOperationGuard.release(
                any(ProjectGraphSync.class),
                any(String.class),
                any(String.class)
        )).thenReturn(true);
    }

    @Test
    void replacesOnlyAfterTargetVersionTitleAndContentAreVerified() throws Exception {
        Fixture fixture = fixture("new title", "new content");
        ProjectGraphSync sync = freshSync();
        stubFresh(fixture, sync);
        ProjectGraphSnapshot snapshot = snapshot(
                fixture, fixture.nodeId(), 4, "new title", "new content"
        );

        GraphProjectionApplyResult result =
                applier.apply(fixture.event(), fixture.graphPayload(), snapshot);

        verify(inboxService).registerProcessed(fixture.event());
        verify(projectionReplacer).replace(1, snapshot, NOW);
        assertThat(result.projectionUpdated()).isTrue();
        assertThat(sync.getCurrentGraphVersion()).isEqualTo(11);
        assertThat(sync.getLastCommandId()).isEqualTo(fixture.commandId().toString());
    }

    @Test
    void titleOnlyDoesNotRequireUnrequestedContentToMatch() throws Exception {
        Fixture fixture = fixture("new title", null);
        ProjectGraphSync sync = freshSync();
        stubFresh(fixture, sync);
        ProjectGraphSnapshot snapshot = snapshot(
                fixture, fixture.nodeId(), 4, "new title", "python content"
        );

        applier.apply(fixture.event(), fixture.graphPayload(), snapshot);

        verify(projectionReplacer).replace(1, snapshot, NOW);
    }

    @Test
    void contentOnlyDoesNotRequireUnrequestedTitleToMatch() throws Exception {
        Fixture fixture = fixture(null, "new content");
        ProjectGraphSync sync = freshSync();
        stubFresh(fixture, sync);
        ProjectGraphSnapshot snapshot = snapshot(
                fixture, fixture.nodeId(), 4, "python title", "new content"
        );

        applier.apply(fixture.event(), fixture.graphPayload(), snapshot);

        verify(projectionReplacer).replace(1, snapshot, NOW);
    }

    @Test
    void staleVersionRemainsIdempotentWithoutRequiringTargetNode() throws Exception {
        Fixture fixture = fixture("new title", "new content");
        ProjectGraphSync sync = ProjectGraphSync.initial(1, Instant.EPOCH);
        sync.advanceTo(11, UUID.randomUUID().toString(), Instant.EPOCH.plusSeconds(1));
        stubCommon(fixture, sync);
        ProjectGraphSnapshot emptySnapshot = snapshot(fixture, List.of(), 10);

        GraphProjectionApplyResult result =
                applier.apply(fixture.event(), fixture.graphPayload(), emptySnapshot);

        assertThat(result.projectionUpdated()).isFalse();
        assertThat(result.currentGraphVersion()).isEqualTo(11);
        verify(projectionReplacer, never()).replace(any(Integer.class), any(), any());
    }

    @Test
    void rejectsEmptyOrMissingTargetNode() throws Exception {
        Fixture fixture = fixture("new title", "new content");
        assertRejected(fixture, snapshot(fixture, List.of(), 11));
        assertRejected(fixture, snapshot(
                fixture,
                List.of(node(UUID.randomUUID().toString(), 4, "new title", "new content")),
                11
        ));
    }

    @ParameterizedTest
    @ValueSource(longs = {3, 2})
    void rejectsNodeVersionThatDidNotAdvance(long nodeVersion) throws Exception {
        Fixture fixture = fixture("new title", "new content");
        assertRejected(fixture, snapshot(
                fixture, fixture.nodeId(), nodeVersion, "new title", "new content"
        ));
    }

    @Test
    void rejectsMismatchedRequestedTitleOrContent() throws Exception {
        Fixture fixture = fixture("new title", "new content");
        assertRejected(fixture, snapshot(
                fixture, fixture.nodeId(), 4, "wrong title", "new content"
        ));
        assertRejected(fixture, snapshot(
                fixture, fixture.nodeId(), 4, "new title", "wrong content"
        ));
    }

    @Test
    void rejectsPayloadNodeCommandIdAndProjectMismatches() throws Exception {
        UUID commandId = UUID.randomUUID();
        String nodeId = UUID.randomUUID().toString();
        assertRejected(fixture(
                commandId, commandId, 1, nodeId, UUID.randomUUID().toString(),
                "title", null, "{\"valid\":true}"
        ), null);
        assertRejected(fixture(
                commandId, UUID.randomUUID(), 1, nodeId, nodeId,
                "title", null, "{\"valid\":true}"
        ), null);
        assertRejected(fixture(
                commandId, commandId, 2, nodeId, nodeId,
                "title", null, "{\"valid\":true}"
        ), null);
    }

    @Test
    void rejectsMalformedPayloadWithoutReplacingProjection() {
        UUID commandId = UUID.randomUUID();
        String nodeId = UUID.randomUUID().toString();
        Fixture fixture = rawFixture(commandId, nodeId, "{not-json");
        ProjectGraphSync sync = freshSync();
        stubCommon(fixture, sync);

        assertThatThrownBy(() -> applier.apply(
                fixture.event(),
                fixture.graphPayload(),
                snapshot(fixture, nodeId, 4, "title", "content")
        )).isInstanceOf(AnalysisResultContractException.class);

        verify(projectionReplacer, never()).replace(any(Integer.class), any(), any());
        assertThat(sync.getCurrentGraphVersion()).isZero();
    }

    private void assertRejected(Fixture fixture, ProjectGraphSnapshot providedSnapshot) {
        ProjectGraphSync sync = freshSync();
        stubCommon(fixture, sync);
        ProjectGraphSnapshot snapshot = providedSnapshot == null
                ? snapshot(fixture, fixture.nodeId(), 4, "title", "content")
                : providedSnapshot;

        assertThatThrownBy(() -> applier.apply(
                fixture.event(), fixture.graphPayload(), snapshot
        )).isInstanceOf(AnalysisResultContractException.class);

        verify(projectionReplacer, never()).replace(any(Integer.class), any(), any());
        assertThat(sync.getCurrentGraphVersion()).isZero();
    }

    private void stubFresh(Fixture fixture, ProjectGraphSync sync) {
        when(projectRepository.findByIdForUpdate(1))
                .thenReturn(Optional.of(Project.builder().title("p").content("c").build()));
        when(commandRepository.findByCommandId(fixture.event().commandId()))
                .thenReturn(Optional.of(fixture.outbox()));
        when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(sync), Optional.of(sync));
    }

    private void stubCommon(Fixture fixture, ProjectGraphSync sync) {
        when(projectRepository.findByIdForUpdate(1))
                .thenReturn(Optional.of(Project.builder().title("p").content("c").build()));
        when(commandRepository.findByCommandId(fixture.event().commandId()))
                .thenReturn(Optional.of(fixture.outbox()));
        lenient().when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(sync));
    }

    private Fixture fixture(String title, String content) throws Exception {
        UUID commandId = UUID.randomUUID();
        String nodeId = UUID.randomUUID().toString();
        NodeContentUpdateRequestedCommand command = command(
                commandId, 1, nodeId, title, content
        );
        return rawFixture(commandId, nodeId, objectMapper.writeValueAsString(command));
    }

    private Fixture fixture(
            UUID outboxCommandId,
            UUID payloadCommandId,
            int payloadProjectId,
            String outboxNodeId,
            String payloadNodeId,
            String title,
            String content,
            String ignored
    ) throws Exception {
        NodeContentUpdateRequestedCommand command = command(
                payloadCommandId, payloadProjectId, payloadNodeId, title, content
        );
        return rawFixture(
                outboxCommandId,
                outboxNodeId,
                objectMapper.writeValueAsString(command)
        );
    }

    private Fixture rawFixture(UUID commandId, String nodeId, String commandJson) {
        MeetingAnalysisCommandOutbox outbox =
                MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                        commandId,
                        1,
                        nodeId,
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        commandJson,
                        15,
                        LocalDateTime.now()
                );
        AnalysisResultEventEnvelope event = new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                NOW,
                1,
                null,
                commandId.toString(),
                objectMapper.createObjectNode()
        );
        return new Fixture(
                commandId,
                nodeId,
                outbox,
                event,
                new ProjectGraphChangedPayload(
                        GraphResultSourceType.NODE_CONTENT_UPDATE,
                        11,
                        null
                )
        );
    }

    private NodeContentUpdateRequestedCommand command(
            UUID commandId,
            int projectId,
            String nodeId,
            String title,
            String content
    ) {
        return new NodeContentUpdateRequestedCommand(
                1,
                commandId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                NOW,
                projectId,
                new NodeContentUpdateRequestedCommand.Payload(
                        nodeId, 3, title, content, 15
                )
        );
    }

    private ProjectGraphSync freshSync() {
        return ProjectGraphSync.initial(1, Instant.EPOCH);
    }

    private ProjectGraphSnapshot snapshot(
            Fixture fixture,
            String nodeId,
            long nodeVersion,
            String title,
            String content
    ) {
        return snapshot(
                fixture,
                List.of(node(nodeId, nodeVersion, title, content)),
                fixture.graphPayload().graphVersion()
        );
    }

    private ProjectGraphSnapshot snapshot(
            Fixture fixture,
            List<ProjectGraphSnapshotNode> nodes,
            long graphVersion
    ) {
        return new ProjectGraphSnapshot(
                1,
                1,
                null,
                fixture.commandId().toString(),
                graphVersion,
                NOW,
                nodes,
                List.of(),
                List.of()
        );
    }

    private ProjectGraphSnapshotNode node(
            String nodeId,
            long nodeVersion,
            String title,
            String content
    ) {
        return new ProjectGraphSnapshotNode(
                nodeId,
                null,
                null,
                null,
                GraphNodeType.DECISION,
                GraphNodeCategory.BACKEND,
                GraphNodeState.ACTIVE,
                title,
                content,
                null,
                nodeVersion,
                NOW,
                NOW
        );
    }

    private record Fixture(
            UUID commandId,
            String nodeId,
            MeetingAnalysisCommandOutbox outbox,
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload graphPayload
    ) {
    }
}
