package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NodeDeleteCommandTest {

    private static final LocalDateTime REQUESTED_AT =
            LocalDateTime.of(2026, 8, 7, 10, 30);
    private static final LocalDateTime COMPLETED_AT = REQUESTED_AT.plusSeconds(2);

    @Test
    void pendingInitializesStateAndCalculatesTotalNodeCount() {
        NodeDeleteCommand command = pending(2, 3);

        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.PENDING);
        assertThat(command.getRequestedNodeCount()).isEqualTo(2);
        assertThat(command.getMergedSourceCount()).isEqualTo(3);
        assertThat(command.getTotalNodeCount()).isEqualTo(5);
        assertThat(command.getReasonCode()).isNull();
        assertThat(command.getResultEventId()).isNull();
        assertThat(command.getResultGraphVersion()).isNull();
        assertThat(command.getCompletedAt()).isNull();
    }

    @Test
    void pendingRejectsInvalidCounts() {
        assertThatThrownBy(() -> pending(0, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> pending(1, -1)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void pendingCanTransitionToSucceeded() {
        NodeDeleteCommand command = pending(1, 0);
        UUID resultEventId = UUID.randomUUID();

        command.markSucceeded(resultEventId, 13, COMPLETED_AT);

        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.SUCCEEDED);
        assertThat(command.getResultEventId()).isEqualTo(resultEventId.toString());
        assertThat(command.getResultGraphVersion()).isEqualTo(13L);
        assertThat(command.getCompletedAt()).isEqualTo(COMPLETED_AT);
    }

    @Test
    void pendingCanTransitionToRejected() {
        NodeDeleteCommand command = pending(1, 0);
        UUID resultEventId = UUID.randomUUID();

        command.markRejected(
                resultEventId,
                NodeDeleteRejectionReason.GRAPH_VERSION_CONFLICT.name(),
                COMPLETED_AT
        );

        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.REJECTED);
        assertThat(command.getResultEventId()).isEqualTo(resultEventId.toString());
        assertThat(command.getReasonCode()).isEqualTo("GRAPH_VERSION_CONFLICT");
        assertThat(command.getCompletedAt()).isEqualTo(COMPLETED_AT);
    }

    @Test
    void pendingCanTransitionToFailed() {
        NodeDeleteCommand command = pending(1, 0);

        command.markFailed("COMMAND_PUBLISH_FAILED", COMPLETED_AT);

        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.FAILED);
        assertThat(command.getReasonCode()).isEqualTo("COMMAND_PUBLISH_FAILED");
        assertThat(command.getCompletedAt()).isEqualTo(COMPLETED_AT);
    }

    @Test
    void terminalStateCannotTransitionAgain() {
        NodeDeleteCommand succeeded = pending(1, 0);
        succeeded.markSucceeded(UUID.randomUUID(), 13, COMPLETED_AT);
        assertThatThrownBy(() -> succeeded.markRejected(
                UUID.randomUUID(),
                "NODE_NOT_FOUND",
                COMPLETED_AT
        )).isInstanceOf(IllegalStateException.class);

        NodeDeleteCommand rejected = pending(1, 0);
        rejected.markRejected(UUID.randomUUID(), "NODE_NOT_FOUND", COMPLETED_AT);
        assertThatThrownBy(() -> rejected.markSucceeded(
                UUID.randomUUID(),
                13,
                COMPLETED_AT
        )).isInstanceOf(IllegalStateException.class);

        NodeDeleteCommand failed = pending(1, 0);
        failed.markFailed("COMMAND_PUBLISH_FAILED", COMPLETED_AT);
        assertThatThrownBy(() -> failed.markSucceeded(
                UUID.randomUUID(),
                13,
                COMPLETED_AT
        )).isInstanceOf(IllegalStateException.class);
    }

    private NodeDeleteCommand pending(int requestedCount, int mergedCount) {
        return NodeDeleteCommand.pending(
                UUID.randomUUID(),
                1,
                12,
                15,
                requestedCount,
                mergedCount,
                REQUESTED_AT
        );
    }
}
