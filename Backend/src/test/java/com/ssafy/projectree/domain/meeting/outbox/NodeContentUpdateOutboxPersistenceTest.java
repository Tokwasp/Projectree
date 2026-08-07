package com.ssafy.projectree.domain.meeting.outbox;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class NodeContentUpdateOutboxPersistenceTest extends IntegrationTestSupport {

    @Autowired
    private MeetingAnalysisCommandOutboxRepository repository;

    @Test
    void storesMultipleCommandsForSameProjectAndNodeWithNullMeeting() {
        String nodeId = UUID.randomUUID().toString();
        MeetingAnalysisCommandOutbox first = nodeOutbox(nodeId);
        MeetingAnalysisCommandOutbox second = nodeOutbox(nodeId);

        repository.saveAndFlush(first);
        repository.saveAndFlush(second);

        assertThat(repository.findByCommandId(first.getCommandId()))
                .get()
                .extracting(MeetingAnalysisCommandOutbox::getMeeting)
                .isNull();
        assertThat(repository.findAll())
                .filteredOn(outbox -> nodeId.equals(outbox.getTargetNodeId()))
                .hasSize(2);
    }

    private MeetingAnalysisCommandOutbox nodeOutbox(String nodeId) {
        return MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                UUID.randomUUID(),
                1,
                nodeId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                "{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}",
                15,
                LocalDateTime.now()
        );
    }
}
