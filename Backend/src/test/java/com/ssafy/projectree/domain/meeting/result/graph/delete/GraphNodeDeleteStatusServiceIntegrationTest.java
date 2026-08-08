package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteStatusResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GraphNodeDeleteStatusServiceIntegrationTest extends IntegrationTestSupport {

    private static final int MEMBER_ID = 15;
    private static final long EXPECTED_GRAPH_VERSION = 12L;
    private static final LocalDateTime REQUESTED_AT =
            LocalDateTime.of(2026, 8, 7, 5, 0);
    private static final LocalDateTime COMPLETED_AT =
            LocalDateTime.of(2026, 8, 7, 5, 0, 2);

    @Autowired
    private GraphNodeDeleteStatusService service;
    @Autowired
    private ProjectRepository projectRepository;
    @Autowired
    private NodeDeleteCommandRepository commandRepository;
    @Autowired
    private NodeDeleteCommandItemRepository itemRepository;

    @Test
    void pendingReturnsOnlyRequestedItemsAndPendingNullFields() {
        int projectId = projectWithMember();
        String requestedA = UUID.randomUUID().toString();
        String requestedB = UUID.randomUUID().toString();
        String mergedSource = UUID.randomUUID().toString();
        NodeDeleteCommand command = pendingCommand(projectId, 2, 1);
        itemRepository.saveAll(List.of(
                NodeDeleteCommandItem.requested(command, requestedA, 1, REQUESTED_AT),
                NodeDeleteCommandItem.mergedSource(command, mergedSource, 2, REQUESTED_AT),
                NodeDeleteCommandItem.requested(command, requestedB, 3, REQUESTED_AT)
        ));

        GraphNodeDeleteStatusResponse response = service.getStatus(
                projectId,
                UUID.fromString(command.getCommandId()),
                MEMBER_ID
        );

        assertThat(response.nodeIds()).containsExactly(requestedA, requestedB);
        assertThat(response.nodeIds()).doesNotContain(mergedSource);
        assertThat(response.status()).isEqualTo(NodeDeleteCommandStatus.PENDING);
        assertThat(response.expectedGraphVersion()).isEqualTo(EXPECTED_GRAPH_VERSION);
        assertThat(response.resultGraphVersion()).isNull();
        assertThat(response.reason()).isNull();
        assertThat(response.requestedAt()).isEqualTo(REQUESTED_AT);
        assertThat(response.completedAt()).isNull();
    }

    @Test
    void succeededReturnsStoredResultGraphVersionAndCompletionTime() {
        int projectId = projectWithMember();
        NodeDeleteCommand command = pendingCommand(projectId, 1, 0);
        command.markSucceeded(UUID.randomUUID(), 13L, COMPLETED_AT);
        commandRepository.saveAndFlush(command);

        GraphNodeDeleteStatusResponse response = service.getStatus(
                projectId,
                UUID.fromString(command.getCommandId()),
                MEMBER_ID
        );

        assertThat(response.status()).isEqualTo(NodeDeleteCommandStatus.SUCCEEDED);
        assertThat(response.resultGraphVersion()).isEqualTo(13L);
        assertThat(response.reason()).isNull();
        assertThat(response.completedAt()).isEqualTo(COMPLETED_AT);
    }

    @ParameterizedTest
    @EnumSource(
            value = NodeDeleteCommandStatus.class,
            names = {"REJECTED", "FAILED"}
    )
    void terminalFailureReturnsStoredReasonWithoutResultVersion(
            NodeDeleteCommandStatus status
    ) {
        int projectId = projectWithMember();
        NodeDeleteCommand command = pendingCommand(projectId, 1, 0);
        String reason = status == NodeDeleteCommandStatus.REJECTED
                ? "GRAPH_VERSION_CONFLICT"
                : "COMMAND_PUBLISH_FAILED";
        if (status == NodeDeleteCommandStatus.REJECTED) {
            command.markRejected(UUID.randomUUID(), reason, COMPLETED_AT);
        } else {
            command.markFailed(reason, COMPLETED_AT);
        }
        commandRepository.saveAndFlush(command);

        GraphNodeDeleteStatusResponse response = service.getStatus(
                projectId,
                UUID.fromString(command.getCommandId()),
                MEMBER_ID
        );

        assertThat(response.status()).isEqualTo(status);
        assertThat(response.reason()).isEqualTo(reason);
        assertThat(response.resultGraphVersion()).isNull();
        assertThat(response.completedAt()).isEqualTo(COMPLETED_AT);
    }

    @Test
    void commandFromAnotherProjectIsReportedAsNotFound() {
        int requestedProjectId = projectWithMember();
        int commandProjectId = projectWithMember();
        NodeDeleteCommand command = pendingCommand(commandProjectId, 1, 0);

        assertThatThrownBy(() -> service.getStatus(
                requestedProjectId,
                UUID.fromString(command.getCommandId()),
                MEMBER_ID
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(GraphNodeDeleteErrorCode.NODE_DELETE_COMMAND_NOT_FOUND);
    }

    private int projectWithMember() {
        Project project = Project.builder()
                .title("project")
                .content("content")
                .build();
        project.addMember(ProjectMember.createMember(MEMBER_ID, ProjectRole.MEMBER));
        return projectRepository.saveAndFlush(project).getId();
    }

    private NodeDeleteCommand pendingCommand(
            int projectId,
            int requestedNodeCount,
            int mergedSourceCount
    ) {
        return commandRepository.saveAndFlush(NodeDeleteCommand.pending(
                UUID.randomUUID(),
                projectId,
                EXPECTED_GRAPH_VERSION,
                MEMBER_ID,
                requestedNodeCount,
                mergedSourceCount,
                REQUESTED_AT
        ));
    }
}
