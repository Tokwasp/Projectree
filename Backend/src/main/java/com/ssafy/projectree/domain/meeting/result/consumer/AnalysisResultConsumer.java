package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventParser;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultRetryableException;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultProcessingOutcome;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventValidator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.sqs.model.Message;

import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnBean(AnalysisResultEventProcessor.class)
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.result-consumer",
        name = "enabled",
        havingValue = "true"
)
public class AnalysisResultConsumer {

    private final AnalysisResultSqsGateway sqsGateway;
    private final AnalysisResultEventParser parser;
    private final AnalysisEventValidator eventValidator;
    private final AnalysisResultEventProcessor processor;

    public void consumeAvailable() {
        List<Message> messages;
        try {
            messages = sqsGateway.receiveMessages();
        } catch (RuntimeException exception) {
            log.error("Failed to receive analysis result messages", exception);
            return;
        }

        if (messages.isEmpty()) {
            log.debug("No analysis result messages received");
            return;
        }

        log.info(
                "[AnalysisFlow] RESULT_SQS_RECEIVED. count={}, messageIds={}",
                messages.size(),
                messages.stream().map(Message::messageId).toList()
        );
        for (Message message : messages) {
            consume(message);
        }
    }

    private void consume(Message message) {
        long startedAt = System.nanoTime();
        try {
            AnalysisResultEventEnvelope event = eventValidator.validateEnvelope(
                    parser.parse(message.body())
            );
            log.info(
                    "[AnalysisFlow] RESULT_PROCESSING_STARTED. messageId={}, approximateReceiveCount={}, eventId={}, eventType={}, commandId={}, projectId={}, meetingId={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    event.eventId(),
                    event.eventType(),
                    event.commandId(),
                    event.projectId(),
                    event.meetingId()
            );
            AnalysisResultProcessingOutcome outcome = processor.process(event);
            if (outcome != AnalysisResultProcessingOutcome.PROCESSED
                    && outcome != AnalysisResultProcessingOutcome.DUPLICATE) {
                throw new IllegalStateException("Analysis result processor returned an unsupported outcome");
            }

            try {
                sqsGateway.deleteMessage(message);
            } catch (RuntimeException exception) {
                log.error(
                        "[AnalysisFlow] RESULT_ACK_FAILED. messageId={}, approximateReceiveCount={}, eventId={}, eventType={}, commandId={}, projectId={}, meetingId={}, outcome={}, elapsedMs={}, exceptionType={}",
                        message.messageId(),
                        approximateReceiveCount(message),
                        event.eventId(),
                        event.eventType(),
                        event.commandId(),
                        event.projectId(),
                        event.meetingId(),
                        outcome,
                        elapsedMillis(startedAt),
                        exception.getClass().getSimpleName(),
                        exception
                );
                return;
            }
            log.info(
                    "[AnalysisFlow] RESULT_ACKNOWLEDGED. messageId={}, approximateReceiveCount={}, eventId={}, eventType={}, commandId={}, projectId={}, meetingId={}, outcome={}, elapsedMs={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    event.eventId(),
                    event.eventType(),
                    event.commandId(),
                    event.projectId(),
                    event.meetingId(),
                    outcome,
                    elapsedMillis(startedAt)
            );
        } catch (AnalysisResultContractException exception) {
            log.warn(
                    "[AnalysisFlow] RESULT_CONTRACT_VIOLATION. messageId={}, approximateReceiveCount={}, elapsedMs={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    elapsedMillis(startedAt),
                    exception
            );
        } catch (AnalysisResultRetryableException | DataAccessException exception) {
            log.warn(
                    "[AnalysisFlow] RESULT_PROCESSING_RETRYABLE_FAILED. messageId={}, approximateReceiveCount={}, elapsedMs={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    elapsedMillis(startedAt),
                    exception
            );
        } catch (RuntimeException exception) {
            log.error(
                    "[AnalysisFlow] RESULT_PROCESSING_UNEXPECTED_FAILED. messageId={}, approximateReceiveCount={}, elapsedMs={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    elapsedMillis(startedAt),
                    exception
            );
        }
    }

    private String approximateReceiveCount(Message message) {
        return message.attributes().getOrDefault("ApproximateReceiveCount", "unknown");
    }

    private long elapsedMillis(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000;
    }
}
