package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingSummaryProjectionTransactionTest extends IntegrationTestSupport {

    @Autowired
    private MeetingSummaryProjectionService service;
    @Autowired
    private MeetingSummaryProjectionRepository repository;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void applyRequiresAnExistingTransaction() {
        assertThatThrownBy(() -> service.apply(event(), payload()))
                .isInstanceOf(IllegalTransactionStateException.class);
    }

    @Test
    void applySucceedsInsideCallerTransaction() {
        AnalysisResultEventEnvelope event = event();
        service.apply(event, payload());

        assertThat(repository.findByMeetingId(event.meetingId())).isPresent();
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.MEETING_SUMMARY_READY,
                Instant.now(), 1, Math.abs(UUID.randomUUID().hashCode()) + 1, UUID.randomUUID().toString(),
                objectMapper.createObjectNode()
        );
    }

    private MeetingSummaryReadyPayload payload() {
        return new MeetingSummaryReadyPayload(
                UUID.randomUUID().toString(), 1, MeetingSummaryResultStatus.READY,
                "/api/v1/meetings/1/summary?summaryVersion=1"
        );
    }
}
