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
                "Received analysis result messages. count={}, messageIds={}",
                messages.size(),
                messages.stream().map(Message::messageId).toList()
        );
        for (Message message : messages) {
            consume(message);
        }
    }

    private void consume(Message message) {
        try {
            AnalysisResultEventEnvelope event = eventValidator.validateEnvelope(
                    parser.parse(message.body())
            );
            AnalysisResultProcessingOutcome outcome = processor.process(event);
            if (outcome != AnalysisResultProcessingOutcome.PROCESSED
                    && outcome != AnalysisResultProcessingOutcome.DUPLICATE) {
                throw new IllegalStateException("Analysis result processor returned an unsupported outcome");
            }

            sqsGateway.deleteMessage(message);
            log.info(
                    "Acknowledged analysis result message. messageId={}, eventId={}, eventType={}, projectId={}, meetingId={}, commandId={}, outcome={}",
                    message.messageId(),
                    event.eventId(),
                    event.eventType(),
                    event.projectId(),
                    event.meetingId(),
                    event.commandId(),
                    outcome
            );
        } catch (AnalysisResultContractException exception) {
            log.warn(
                    "Analysis result contract violation; message will not be acknowledged. messageId={}, approximateReceiveCount={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    exception
            );
        } catch (AnalysisResultRetryableException | DataAccessException exception) {
            log.warn(
                    "Retryable analysis result processing failure; message will not be acknowledged. messageId={}, approximateReceiveCount={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    exception
            );
        } catch (RuntimeException exception) {
            log.error(
                    "Unexpected analysis result processing failure; message will not be acknowledged. messageId={}, approximateReceiveCount={}",
                    message.messageId(),
                    approximateReceiveCount(message),
                    exception
            );
        }
    }

    private String approximateReceiveCount(Message message) {
        return message.attributes().getOrDefault("ApproximateReceiveCount", "unknown");
    }
}
