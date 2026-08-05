package com.ssafy.projectree.domain.meeting.result.inbox;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.DuplicateAnalysisResultEventException;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ResultInboxServiceIntegrationTest extends IntegrationTestSupport {

    @Autowired
    private ResultInboxService resultInboxService;

    @Autowired
    private MeetingAnalysisResultInboxRepository inboxRepository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void registersDistinctEventsAndSupportsAdvisoryDuplicateLookup() {
        AnalysisResultEventEnvelope first = event();
        AnalysisResultEventEnvelope second = event();

        resultInboxService.registerProcessed(first);
        assertThat(resultInboxService.isProcessed(first.eventId())).isTrue();
        resultInboxService.registerProcessed(second);

        assertThat(inboxRepository.existsByEventId(second.eventId())).isTrue();
    }

    @Test
    void translatesOnlyEventIdUniqueCollisionToDuplicateException() {
        AnalysisResultEventEnvelope event = event();
        resultInboxService.registerProcessed(event);

        assertThatThrownBy(() -> resultInboxService.registerProcessed(event))
                .isInstanceOf(DuplicateAnalysisResultEventException.class);
    }

    @Test
    void rollsBackInboxInsertWhenTheOwningEventTransactionFails() {
        AnalysisResultEventEnvelope event = event();
        TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);
        transactionTemplate.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
            resultInboxService.registerProcessed(event);
            throw new IllegalStateException("projection failed");
        })).isInstanceOf(IllegalStateException.class);

        assertThat(inboxRepository.existsByEventId(event.eventId())).isFalse();
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.parse("2026-08-04T12:30:00Z"),
                1,
                1,
                UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
    }
}
