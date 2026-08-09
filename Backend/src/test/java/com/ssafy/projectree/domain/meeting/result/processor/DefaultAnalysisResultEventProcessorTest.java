package com.ssafy.projectree.domain.meeting.result.processor;

import com.ssafy.projectree.domain.meeting.result.dispatcher.AnalysisResultEventDispatcher;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultHandlerUnavailableException;
import com.ssafy.projectree.domain.meeting.result.exception.DuplicateAnalysisResultEventException;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventReferenceValidator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.inOrder;

@ExtendWith(MockitoExtension.class)
class DefaultAnalysisResultEventProcessorTest {

    @Mock
    private ResultInboxService inboxService;
    @Mock
    private AnalysisResultEventDispatcher dispatcher;
    @Mock
    private AnalysisEventReferenceValidator referenceValidator;

    @Test
    void returnsDuplicateForAdvisoryOrUniqueCollisionDuplicates() {
        DefaultAnalysisResultEventProcessor processor = processor();
        AnalysisResultEventEnvelope event = event();
        given(inboxService.isProcessed(event.eventId())).willReturn(true);

        assertThat(processor.process(event)).isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);
        verify(referenceValidator, never()).validateReferences(any());
        verify(dispatcher, never()).dispatch(any());

        AnalysisResultEventEnvelope racingDuplicate = event();
        given(inboxService.isProcessed(racingDuplicate.eventId())).willReturn(false);
        doNothing().when(referenceValidator).validateReferences(racingDuplicate);
        doThrow(new DuplicateAnalysisResultEventException(racingDuplicate.eventId(), null))
                .when(dispatcher).dispatch(racingDuplicate);
        assertThat(processor.process(racingDuplicate))
                .isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);
    }

    @Test
    void returnsProcessedOnlyAfterDispatcherCompletesAndPropagatesUnavailableHandler() {
        DefaultAnalysisResultEventProcessor processor = processor();
        AnalysisResultEventEnvelope event = event();
        given(inboxService.isProcessed(event.eventId())).willReturn(false);
        doNothing().when(referenceValidator).validateReferences(event);
        doNothing().when(dispatcher).dispatch(event);

        assertThat(processor.process(event)).isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        org.mockito.InOrder order = inOrder(inboxService, referenceValidator, dispatcher);
        order.verify(inboxService).isProcessed(event.eventId());
        order.verify(referenceValidator).validateReferences(event);
        order.verify(dispatcher).dispatch(event);

        AnalysisResultEventEnvelope unavailable = event();
        given(inboxService.isProcessed(unavailable.eventId())).willReturn(false);
        doNothing().when(referenceValidator).validateReferences(unavailable);
        doThrow(new AnalysisResultHandlerUnavailableException("not implemented"))
                .when(dispatcher).dispatch(unavailable);
        assertThatThrownBy(() -> processor.process(unavailable))
                .isInstanceOf(AnalysisResultHandlerUnavailableException.class);
    }

    @Test
    void stopsBeforeDispatchWhenReferenceValidationFails() {
        DefaultAnalysisResultEventProcessor processor = processor();
        AnalysisResultEventEnvelope event = event();
        given(inboxService.isProcessed(event.eventId())).willReturn(false);
        doThrow(new AnalysisResultContractException("invalid reference"))
                .when(referenceValidator).validateReferences(event);

        assertThatThrownBy(() -> processor.process(event))
                .isInstanceOf(AnalysisResultContractException.class);
        verify(dispatcher, never()).dispatch(any());
    }

    private DefaultAnalysisResultEventProcessor processor() {
        return new DefaultAnalysisResultEventProcessor(inboxService, referenceValidator, dispatcher);
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED,
                Instant.now(), 1, 1, UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
    }
}
