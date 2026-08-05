package com.ssafy.projectree.domain.meeting.outbox.sender;

import com.ssafy.projectree.domain.meeting.outbox.config.MeetingAnalysisPublisherProperties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

class SqsMeetingAnalysisCommandSenderTest {

    @Test
    void sendsStoredPayloadUnchangedWithSameCommandIdOnRetry() {
        SqsClient sqsClient = mock(SqsClient.class);
        MeetingAnalysisPublisherProperties properties = properties();
        SqsMeetingAnalysisCommandSender sender =
                new SqsMeetingAnalysisCommandSender(sqsClient, properties);
        String commandId = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";
        String payload = "{ \"spacing\": \"must stay identical\", \"value\": 1 }";

        sender.send(commandId, payload);
        sender.send(commandId, payload);

        ArgumentCaptor<SendMessageRequest> captor =
                ArgumentCaptor.forClass(SendMessageRequest.class);
        verify(sqsClient, times(2)).sendMessage(captor.capture());
        assertThat(captor.getAllValues()).allSatisfy(request -> {
            assertThat(request.queueUrl()).isEqualTo(properties.queueUrl());
            assertThat(request.messageBody()).isEqualTo(payload);
            assertThat(request.messageAttributes().get("commandId").stringValue())
                    .isEqualTo(commandId);
        });
    }

    private MeetingAnalysisPublisherProperties properties() {
        return new MeetingAnalysisPublisherProperties(
                true, 1000, 20, 3, 60, 30, 120, 5, 10,
                "https://sqs.ap-northeast-2.amazonaws.com/000000000000/staging",
                "ap-northeast-2"
        );
    }
}
