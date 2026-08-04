package com.ssafy.projectree.domain.meeting.outbox.sender;

import com.ssafy.projectree.domain.meeting.outbox.config.MeetingAnalysisPublisherProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.MessageAttributeValue;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

import java.util.Map;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.publisher",
        name = "enabled",
        havingValue = "true"
)
public class SqsMeetingAnalysisCommandSender implements MeetingAnalysisCommandSender {

    private final SqsClient sqsClient;
    private final MeetingAnalysisPublisherProperties properties;

    @Override
    public void send(String commandId, String payload) {
        SendMessageRequest request = SendMessageRequest.builder()
                .queueUrl(properties.queueUrl())
                .messageBody(payload)
                .messageAttributes(Map.of(
                        "commandId",
                        MessageAttributeValue.builder()
                                .dataType("String")
                                .stringValue(commandId)
                                .build()
                ))
                .build();
        sqsClient.sendMessage(request);
    }
}
