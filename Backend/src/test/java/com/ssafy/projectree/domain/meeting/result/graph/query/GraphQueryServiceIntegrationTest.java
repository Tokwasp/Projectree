package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphMergedSourcesResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodePageResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.sql.Connection;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

class GraphQueryServiceIntegrationTest extends IntegrationTestSupport {

    private static final int OWNER_ID = 101;
    private static final int MEMBER_ID = 102;
    private static final int OUTSIDER_ID = 103;

    @Autowired private GraphQueryService graphQueryService;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;
    @MockitoSpyBean private NodeEvidenceProjectionRepository evidenceRepositorySpy;
    @MockitoSpyBean private ProjectRepository projectRepositorySpy;

    @Test
    void ownerAndMemberCanReadActiveTreeWhileOutsiderIsRejectedBeforeNodeLookup() {
        Fixture fixture = fixture(true);
        ProjectNodeProjection active = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        saveNode(fixture.projectId(), fixture.meetingId(), "20000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.DESIGN, GraphNodeState.UNATTACHED, 2);

        GraphTreeResponse ownerTree = graphQueryService.getTree(fixture.projectId(), OWNER_ID);
        GraphTreeResponse memberTree = graphQueryService.getTree(fixture.projectId(), MEMBER_ID);

        assertThat(ownerTree.graphVersion()).isEqualTo(5);
        assertThat(ownerTree.root().title()).isEqualTo("query-project");
        assertThat(ownerTree.root().children().getFirst().children()).extracting(node -> node.id())
                .containsExactly(active.getNodeId());
        assertThat(memberTree.root().children()).hasSize(6);
        assertProjectParticipantError(() -> graphQueryService.getTree(fixture.projectId(), OUTSIDER_ID));
    }

    @Test
    void returnsVersionZeroAndEmptyTreeWhenGraphSyncDoesNotExist() {
        Fixture fixture = fixture(false);

        GraphTreeResponse response = graphQueryService.getTree(fixture.projectId(), OWNER_ID);

        assertThat(response.graphVersion()).isZero();
        assertThat(response.graphSyncedAt()).isNull();
        assertThat(response.root().children()).hasSize(6);
        assertThat(response.root().children()).allSatisfy(category -> assertThat(category.children()).isEmpty());
    }

    @Test
    void rejectsProjectionWhenSyncIsMissingButNodesExistForEveryGraphQuery() {
        Fixture fixture = fixture(false);
        ProjectNodeProjection node = saveNode(
                fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1
        );

        assertProjectionInconsistentForEveryGraphQuery(fixture, node.getNodeId());
    }

    @Test
    void rejectsProjectionWhenSyncVersionIsZeroButNodesExistForEveryGraphQuery() {
        Fixture fixture = fixture(false);
        graphSyncRepository.saveAndFlush(ProjectGraphSync.initial(
                fixture.projectId(), Instant.parse("2026-08-05T00:00:00Z")
        ));
        ProjectNodeProjection node = saveNode(
                fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1
        );

        assertProjectionInconsistentForEveryGraphQuery(fixture, node.getNodeId());
    }

    @Test
    void returnsEmptyResultsWhenSyncVersionIsZeroAndNodesDoNotExist() {
        Fixture fixture = fixture(false);
        Instant syncedAt = Instant.parse("2026-08-05T00:00:00Z");
        graphSyncRepository.saveAndFlush(ProjectGraphSync.initial(fixture.projectId(), syncedAt));

        GraphTreeResponse tree = graphQueryService.getTree(fixture.projectId(), OWNER_ID);
        GraphNodePageResponse page = graphQueryService.getUnattachedNodes(
                fixture.projectId(), OWNER_ID, "UNATTACHED", 0, 20
        );

        assertThat(tree.graphVersion()).isZero();
        assertThat(tree.graphSyncedAt()).isEqualTo(syncedAt);
        assertThat(tree.root().children()).allSatisfy(category -> assertThat(category.children()).isEmpty());
        assertThat(page.graphVersion()).isZero();
        assertThat(page.graphSyncedAt()).isEqualTo(syncedAt);
        assertThat(page.items()).isEmpty();
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void usesRepeatableReadReadOnlyTransactionThroughSpringProxy() {
        AtomicReference<TransactionObservation> observation = new AtomicReference<>();
        doAnswer(invocation -> {
            observation.set(new TransactionObservation(
                    TransactionSynchronizationManager.isActualTransactionActive(),
                    TransactionSynchronizationManager.isCurrentTransactionReadOnly(),
                    TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()
            ));
            return Optional.empty();
        }).when(projectRepositorySpy).findById(-1);

        assertThat(AopUtils.isAopProxy(graphQueryService)).isTrue();
        assertThatThrownBy(() -> graphQueryService.getTree(-1, OWNER_ID))
                .isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);

        assertThat(observation.get()).isNotNull();
        assertThat(observation.get().transactionActive()).isTrue();
        assertThat(observation.get().readOnly()).isTrue();
        assertThat(observation.get().isolationLevel()).isEqualTo(Connection.TRANSACTION_REPEATABLE_READ);
    }

    @Test
    void listsOnlyUnattachedNodesWithFixedSortPaginationAndRejectsOtherStates() {
        Fixture fixture = fixture(true);
        ProjectNodeProjection newest = saveNode(fixture.projectId(), fixture.meetingId(), "30000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.UNATTACHED, 3);
        ProjectNodeProjection older = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.UNATTACHED, 1);
        saveNode(fixture.projectId(), fixture.meetingId(), "20000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 2);

        GraphNodePageResponse page = graphQueryService.getUnattachedNodes(
                fixture.projectId(), OWNER_ID, "UNATTACHED", 0, 1
        );

        assertThat(page.totalElements()).isEqualTo(2);
        assertThat(page.items()).extracting(item -> item.nodeId()).containsExactly(newest.getNodeId());
        assertThat(older.getNodeId()).isNotEqualTo(newest.getNodeId());
        assertThatThrownBy(() -> graphQueryService.getUnattachedNodes(
                fixture.projectId(), OWNER_ID, "ACTIVE", 0, 20
        )).isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(GraphQueryErrorCode.INVALID_GRAPH_STATE_QUERY);
        assertThatThrownBy(() -> graphQueryService.getUnattachedNodes(
                fixture.projectId(), OWNER_ID, null, 0, 20
        )).isInstanceOf(CustomException.class);
    }

    @Test
    void returnsNodeDetailForEveryStateWithEvidenceInStableOrder() {
        Fixture fixture = fixture(true);
        ProjectNodeProjection merged = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, "target", GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.MERGED, 1);
        saveEvidence("30000000-0000-0000-0000-000000000000", merged.getNodeId(), 2, "second");
        saveEvidence("20000000-0000-0000-0000-000000000000", merged.getNodeId(), 1, "first");

        GraphNodeDetailResponse response = graphQueryService.getNodeDetail(
                fixture.projectId(), merged.getNodeId(), MEMBER_ID
        );

        assertThat(response.graphVersion()).isEqualTo(5);
        assertThat(response.node().content()).isEqualTo("content-1");
        assertThat(response.node().mergedIntoNodeId()).isEqualTo("target");
        assertThat(response.node().evidences()).extracting(evidence -> evidence.quoteText())
                .containsExactly("first", "second");
    }

    @Test
    void returnsMergedSourcesWithOneBatchEvidenceQueryAndStableSort() {
        Fixture fixture = fixture(true);
        ProjectNodeProjection target = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection later = saveNode(fixture.projectId(), fixture.meetingId(), "30000000-0000-0000-0000-000000000000",
                null, target.getNodeId(), GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.MERGED, 3);
        ProjectNodeProjection earlier = saveNode(fixture.projectId(), fixture.meetingId(), "20000000-0000-0000-0000-000000000000",
                null, target.getNodeId(), GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.MERGED, 2);
        saveEvidence("40000000-0000-0000-0000-000000000000", earlier.getNodeId(), 1, "source-evidence");

        GraphMergedSourcesResponse response = graphQueryService.getMergedSources(
                fixture.projectId(), target.getNodeId(), OWNER_ID
        );

        assertThat(response.items()).extracting(item -> item.nodeId())
                .containsExactly(earlier.getNodeId(), later.getNodeId());
        assertThat(response.items().getFirst().evidences()).extracting(evidence -> evidence.quoteText())
                .containsExactly("source-evidence");
        verify(evidenceRepositorySpy, times(1)).findAllByNodeIdIn(org.mockito.ArgumentMatchers.anyCollection());
    }

    @Test
    void doesNotQueryEvidenceBatchWhenMergedSourcesDoNotExist() {
        Fixture fixture = fixture(true);
        ProjectNodeProjection target = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        clearInvocations(evidenceRepositorySpy);

        GraphMergedSourcesResponse response = graphQueryService.getMergedSources(
                fixture.projectId(), target.getNodeId(), OWNER_ID
        );

        assertThat(response.items()).isEmpty();
        verify(evidenceRepositorySpy, never()).findAllByNodeIdIn(anyCollection());
    }

    @Test
    void listsNodesCreatedByMeetingAcrossEveryGraphStateAndRejectsProjectMismatch() {
        Fixture fixture = fixture(true);
        Meeting otherMeeting = meetingRepository.saveAndFlush(Meeting.create(
                fixture.project(), fixture.creator(), UUID.randomUUID().toString()
        ));
        ProjectNodeProjection active = saveNode(fixture.projectId(), fixture.meetingId(), "10000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection merged = saveNode(fixture.projectId(), fixture.meetingId(), "20000000-0000-0000-0000-000000000000",
                null, active.getNodeId(), GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.MERGED, 2);
        saveNode(fixture.projectId(), otherMeeting.getId(), "30000000-0000-0000-0000-000000000000",
                null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.UNATTACHED, 3);

        GraphNodePageResponse response = graphQueryService.getMeetingNodes(
                fixture.projectId(), fixture.meetingId(), MEMBER_ID, 0, 20
        );

        assertThat(response.items()).extracting(item -> item.nodeId())
                .containsExactly(active.getNodeId(), merged.getNodeId());

        Project otherProject = projectRepository.saveAndFlush(Project.builder().title("other").content("content").build());
        ProjectMember otherOwner = ProjectMember.createMember(999, ProjectRole.OWNER);
        otherProject.addMember(otherOwner);
        otherProject = projectRepository.saveAndFlush(otherProject);
        Meeting foreignMeeting = meetingRepository.saveAndFlush(Meeting.create(
                otherProject, otherOwner, UUID.randomUUID().toString()
        ));
        assertThatThrownBy(() -> graphQueryService.getMeetingNodes(
                fixture.projectId(), foreignMeeting.getId(), OWNER_ID, 0, 20
        )).isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode.MEETING_PROJECT_MISMATCH);
    }

    private Fixture fixture(boolean withGraphSync) {
        Project project = Project.builder().title("query-project").content("content").build();
        ProjectMember owner = ProjectMember.createMember(OWNER_ID, ProjectRole.OWNER);
        project.addMember(owner);
        project.addMember(ProjectMember.createMember(MEMBER_ID, ProjectRole.MEMBER));
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = meetingRepository.saveAndFlush(Meeting.create(project, owner, UUID.randomUUID().toString()));
        if (withGraphSync) {
            ProjectGraphSync sync = ProjectGraphSync.initial(project.getId(), Instant.parse("2026-08-05T00:00:00Z"));
            sync.advanceTo(5, UUID.randomUUID().toString(), Instant.parse("2026-08-05T00:00:05Z"));
            graphSyncRepository.saveAndFlush(sync);
        }
        return new Fixture(project, owner, project.getId(), meeting.getId());
    }

    private ProjectNodeProjection saveNode(
            int projectId,
            int meetingId,
            String nodeId,
            String parentNodeId,
            String mergedIntoNodeId,
            GraphNodeType type,
            GraphNodeCategory category,
            GraphNodeState state,
            long second
    ) {
        Instant timestamp = Instant.parse("2026-08-05T00:00:0" + second + "Z");
        return nodeRepository.saveAndFlush(ProjectNodeProjection.from(projectId, new ProjectGraphSnapshotNode(
                nodeId, meetingId, parentNodeId, mergedIntoNodeId, type, category, state,
                "title-" + second, "content-" + second, GraphLinkSource.AI, second, timestamp, timestamp
        ), timestamp));
    }

    private void saveEvidence(String evidenceId, String nodeId, int order, String quote) {
        Instant now = Instant.parse("2026-08-05T00:00:10Z");
        evidenceRepository.saveAndFlush(NodeEvidenceProjection.from(new ProjectGraphSnapshotEvidence(
                evidenceId, nodeId, 1, quote, null, null, null, order
        ), now));
    }

    private void assertProjectParticipantError(Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
    }

    private void assertProjectionInconsistentForEveryGraphQuery(Fixture fixture, String nodeId) {
        assertProjectionInconsistent(() -> graphQueryService.getTree(fixture.projectId(), OWNER_ID));
        assertProjectionInconsistent(() -> graphQueryService.getUnattachedNodes(
                fixture.projectId(), OWNER_ID, "UNATTACHED", 0, 20
        ));
        assertProjectionInconsistent(() -> graphQueryService.getNodeDetail(
                fixture.projectId(), nodeId, OWNER_ID
        ));
        assertProjectionInconsistent(() -> graphQueryService.getMergedSources(
                fixture.projectId(), nodeId, OWNER_ID
        ));
        assertProjectionInconsistent(() -> graphQueryService.getMeetingNodes(
                fixture.projectId(), fixture.meetingId(), OWNER_ID, 0, 20
        ));
    }

    private void assertProjectionInconsistent(Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT);
    }

    private record Fixture(Project project, ProjectMember creator, int projectId, int meetingId) {
    }

    private record TransactionObservation(
            boolean transactionActive,
            boolean readOnly,
            Integer isolationLevel
    ) {
    }
}
