package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventParser;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultRetryableException;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultHandlerUnavailableException;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultProcessingOutcome;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventValidator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class AnalysisResultConsumerTest {

    @Mock
    private AnalysisResultSqsGateway sqsGateway;

    @Mock
    private AnalysisResultEventParser parser;

    @Mock
    private AnalysisEventValidator eventValidator;

    @Mock
    private AnalysisResultEventProcessor processor;

    private AnalysisResultConsumer consumer;

    @BeforeEach
    void setUp() {
        consumer = new AnalysisResultConsumer(
                sqsGateway, parser, eventValidator, processor
        );
    }

    @Test
    void acknowledgesProcessedAndDuplicateOutcomes() {
        Message processed = message("processed");
        Message duplicate = message("duplicate");
        given(sqsGateway.receiveMessages()).willReturn(List.of(processed, duplicate));
        given(parser.parse(any())).willReturn(event());
        given(eventValidator.validateEnvelope(any())).willAnswer(invocation -> invocation.getArgument(0));
        given(processor.process(any()))
                .willReturn(AnalysisResultProcessingOutcome.PROCESSED)
                .willReturn(AnalysisResultProcessingOutcome.DUPLICATE);

        consumer.consumeAvailable();

        verify(sqsGateway).deleteMessage(processed);
        verify(sqsGateway).deleteMessage(duplicate);
    }

    @Test
    void doesNotProcessMessagesWhenQueueIsEmpty() {
        given(sqsGateway.receiveMessages()).willReturn(List.of());

        consumer.consumeAvailable();

        verifyNoInteractions(parser, eventValidator, processor);
    }

    @Test
    void doesNotAcknowledgeContractRetryableOrUnexpectedFailures() {
        Message contractFailure = message("contract");
        Message retryableFailure = message("retryable");
        Message unexpectedFailure = message("unexpected");
        given(sqsGateway.receiveMessages()).willReturn(List.of(
                contractFailure, retryableFailure, unexpectedFailure
        ));
        given(parser.parse(contractFailure.body()))
                .willThrow(new AnalysisResultContractException("invalid"));
        given(parser.parse(retryableFailure.body())).willReturn(event());
        given(parser.parse(unexpectedFailure.body())).willReturn(event());
        given(eventValidator.validateEnvelope(any())).willAnswer(invocation -> invocation.getArgument(0));
        given(processor.process(any()))
                .willThrow(new AnalysisResultRetryableException(
                        "temporary", new IllegalStateException("database unavailable")
                ))
                .willThrow(new IllegalStateException("unexpected"));

        consumer.consumeAvailable();

        verify(sqsGateway, never()).deleteMessage(any());
    }

    @Test
    void doesNotAcknowledgeUnavailableGraphHandler() {
        Message graph = message("graph");
        given(sqsGateway.receiveMessages()).willReturn(List.of(graph));
        given(parser.parse(graph.body())).willReturn(event());
        given(eventValidator.validateEnvelope(any())).willAnswer(invocation -> invocation.getArgument(0));
        given(processor.process(any()))
                .willThrow(new AnalysisResultHandlerUnavailableException("Graph handler is not implemented"));

        consumer.consumeAvailable();

        verify(sqsGateway, never()).deleteMessage(any());
    }

    @Test
    void continuesWithNextMessageWhenDeleteOrPreviousMessageProcessingFails() {
        Message first = message("first");
        Message second = message("second");
        given(sqsGateway.receiveMessages()).willReturn(List.of(first, second));
        given(parser.parse(any())).willReturn(event());
        given(eventValidator.validateEnvelope(any())).willAnswer(invocation -> invocation.getArgument(0));
        given(processor.process(any())).willReturn(AnalysisResultProcessingOutcome.PROCESSED);
        doThrow(new IllegalStateException("SQS temporary failure"))
                .doNothing()
                .when(sqsGateway).deleteMessage(any());

        consumer.consumeAvailable();

        verify(sqsGateway, times(2)).deleteMessage(any());
    }

    private Message message(String suffix) {
        return Message.builder()
                .messageId("message-" + suffix)
                .body("body-" + suffix)
                .attributes(java.util.Map.of(
                        MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT,
                        "1"
                ))
                .receiptHandle("receipt-" + suffix)
                .build();
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(),
                1,
                1,
                UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
    }
}
