package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NodeDeleteRepositoryTest extends IntegrationTestSupport {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 7, 10, 30);

    @Autowired
    private NodeDeleteCommandRepository commandRepository;

    @Autowired
    private NodeDeleteCommandItemRepository itemRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void storesCommandAndItemsAndFindsByBusinessKeys() {
        UUID commandId = UUID.randomUUID();
        NodeDeleteCommand command = commandRepository.saveAndFlush(pending(commandId, 1, 2));
        String requestedId = UUID.randomUUID().toString();
        String mergedId = UUID.randomUUID().toString();
        itemRepository.saveAllAndFlush(java.util.List.of(
                NodeDeleteCommandItem.requested(command, requestedId, 3, NOW),
                NodeDeleteCommandItem.mergedSource(command, mergedId, 1, NOW)
        ));

        assertThat(commandRepository.findByCommandId(commandId.toString())).isPresent();
        assertThat(commandRepository.findByProjectIdAndCommandId(1, commandId.toString()))
                .isPresent();
        assertThat(commandRepository.existsByProjectIdAndStatus(
                1,
                NodeDeleteCommandStatus.PENDING
        )).isTrue();
        assertThat(itemRepository.findAllByCommandId(commandId.toString()))
                .extracting(NodeDeleteCommandItem::getNodeId)
                .containsExactly(requestedId, mergedId);
    }

    @Test
    void commandIdIsUnique() {
        UUID commandId = UUID.randomUUID();
        commandRepository.saveAndFlush(pending(commandId, 1, 1));

        assertThatThrownBy(() -> commandRepository.saveAndFlush(pending(commandId, 2, 1)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void commandAndNodeIdPairIsUnique() {
        NodeDeleteCommand command =
                commandRepository.saveAndFlush(pending(UUID.randomUUID(), 1, 2));
        String nodeId = UUID.randomUUID().toString();
        itemRepository.saveAndFlush(NodeDeleteCommandItem.requested(command, nodeId, 1, NOW));

        assertThatThrownBy(() -> itemRepository.saveAndFlush(
                NodeDeleteCommandItem.mergedSource(command, nodeId, 1, NOW)
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void pendingNodeIdsIncludeBothItemTypesOnlyForTheSelectedProject() {
        NodeDeleteCommand pending = saveWithItems(1, NodeDeleteCommandStatus.PENDING);
        String requestedId = itemRepository.findRequestedNodeIdsByCommandId(
                pending.getCommandId()
        ).getFirst();
        String mergedId = itemRepository.findAllByCommandId(pending.getCommandId()).stream()
                .filter(item -> item.getItemType() == NodeDeleteItemType.MERGED_SOURCE)
                .findFirst()
                .orElseThrow()
                .getNodeId();

        saveWithItems(2, NodeDeleteCommandStatus.PENDING);
        saveWithItems(1, NodeDeleteCommandStatus.SUCCEEDED);
        saveWithItems(1, NodeDeleteCommandStatus.REJECTED);
        saveWithItems(1, NodeDeleteCommandStatus.FAILED);

        assertThat(itemRepository.findPendingNodeIdsByProjectId(1))
                .containsExactlyInAnyOrder(requestedId, mergedId);
    }

    @Test
    void statusLookupReturnsRequestedItemsWithoutMergedSources() {
        NodeDeleteCommand command = saveWithItems(1, NodeDeleteCommandStatus.PENDING);

        assertThat(itemRepository.findRequestedNodeIdsByCommandId(command.getCommandId()))
                .singleElement()
                .isEqualTo(itemRepository.findAllByCommandCommandIdAndItemTypeOrderById(
                        command.getCommandId(),
                        NodeDeleteItemType.REQUESTED
                ).getFirst().getNodeId());
    }

    @Test
    void preservesGraphAndNodeVersionsAboveIntegerRangeInDatabase() {
        long expectedGraphVersion = (long) Integer.MAX_VALUE + 10L;
        long resultGraphVersion = expectedGraphVersion + 1L;
        long expectedNodeVersion = expectedGraphVersion + 2L;
        UUID commandId = UUID.randomUUID();
        NodeDeleteCommand command = NodeDeleteCommand.pending(
                commandId,
                1,
                expectedGraphVersion,
                15,
                1,
                0,
                NOW
        );
        command.markSucceeded(UUID.randomUUID(), resultGraphVersion, NOW.plusSeconds(2));
        commandRepository.saveAndFlush(command);
        itemRepository.saveAndFlush(NodeDeleteCommandItem.requested(
                command,
                UUID.randomUUID().toString(),
                expectedNodeVersion,
                NOW
        ));
        entityManager.clear();

        NodeDeleteCommand found = commandRepository.findByCommandId(commandId.toString())
                .orElseThrow();
        NodeDeleteCommandItem foundItem = itemRepository
                .findAllByCommandId(commandId.toString())
                .getFirst();
        assertThat(found.getExpectedGraphVersion()).isEqualTo(expectedGraphVersion);
        assertThat(found.getResultGraphVersion()).isEqualTo(resultGraphVersion);
        assertThat(foundItem.getExpectedNodeVersion()).isEqualTo(expectedNodeVersion);
    }

    @Test
    void pendingNodeIdQueryReturnsDistinctValuesAcrossCommands() {
        String nodeId = UUID.randomUUID().toString();
        NodeDeleteCommand first = commandRepository.saveAndFlush(
                pending(UUID.randomUUID(), 1, 1)
        );
        NodeDeleteCommand second = commandRepository.saveAndFlush(
                pending(UUID.randomUUID(), 1, 1)
        );
        itemRepository.saveAllAndFlush(java.util.List.of(
                NodeDeleteCommandItem.requested(first, nodeId, 1, NOW),
                NodeDeleteCommandItem.requested(second, nodeId, 1, NOW)
        ));

        assertThat(itemRepository.findPendingNodeIdsByProjectId(1))
                .containsExactly(nodeId);
    }

    private NodeDeleteCommand saveWithItems(int projectId, NodeDeleteCommandStatus status) {
        NodeDeleteCommand command = pending(UUID.randomUUID(), projectId, 2);
        if (status == NodeDeleteCommandStatus.SUCCEEDED) {
            command.markSucceeded(UUID.randomUUID(), 13, NOW.plusSeconds(2));
        } else if (status == NodeDeleteCommandStatus.REJECTED) {
            command.markRejected(UUID.randomUUID(), "NODE_NOT_FOUND", NOW.plusSeconds(2));
        } else if (status == NodeDeleteCommandStatus.FAILED) {
            command.markFailed("COMMAND_PUBLISH_FAILED", NOW.plusSeconds(2));
        }
        commandRepository.saveAndFlush(command);
        itemRepository.saveAllAndFlush(java.util.List.of(
                NodeDeleteCommandItem.requested(
                        command,
                        UUID.randomUUID().toString(),
                        3,
                        NOW
                ),
                NodeDeleteCommandItem.mergedSource(
                        command,
                        UUID.randomUUID().toString(),
                        2,
                        NOW
                )
        ));
        return command;
    }

    private NodeDeleteCommand pending(UUID commandId, int projectId, int totalItems) {
        return NodeDeleteCommand.pending(
                commandId,
                projectId,
                12,
                15,
                1,
                totalItems - 1,
                NOW
        );
    }
}
