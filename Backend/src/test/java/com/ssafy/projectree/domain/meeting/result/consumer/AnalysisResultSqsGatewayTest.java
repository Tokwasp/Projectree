package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.config.AnalysisResultConsumerProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

import java.util.List;
import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AnalysisResultSqsGatewayTest {

    private static final String QUEUE_URL = "https://example.invalid/result-queue";

    @Mock private SqsClient sqsClient;

    @Test
    void receivesAndDeletesMessagesUsingConfiguredQueueUrl() {
        AnalysisResultSqsGateway gateway = new AnalysisResultSqsGateway(
                sqsClient,
                new AnalysisResultConsumerProperties(true, QUEUE_URL, 20, 10, 1000, "ap-northeast-2")
        );
        Message message = Message.builder().receiptHandle("receipt").build();
        when(sqsClient.receiveMessage(any(ReceiveMessageRequest.class))).thenReturn(
                ReceiveMessageResponse.builder().messages(List.of(message)).build()
        );

        assertThat(gateway.receiveMessages()).containsExactly(message);
        gateway.deleteMessage(message);

        ArgumentCaptor<ReceiveMessageRequest> receiveRequest = ArgumentCaptor.forClass(ReceiveMessageRequest.class);
        verify(sqsClient).receiveMessage(receiveRequest.capture());
        assertThat(receiveRequest.getValue().queueUrl()).isEqualTo(QUEUE_URL);
        assertThat(receiveRequest.getValue().waitTimeSeconds()).isEqualTo(20);
        assertThat(receiveRequest.getValue().maxNumberOfMessages()).isEqualTo(10);

        @SuppressWarnings({"unchecked", "rawtypes"})
        ArgumentCaptor<Consumer<DeleteMessageRequest.Builder>> deleteRequestCustomizer =
                (ArgumentCaptor) ArgumentCaptor.forClass(Consumer.class);
        verify(sqsClient).deleteMessage(deleteRequestCustomizer.capture());
        DeleteMessageRequest.Builder deleteRequestBuilder = DeleteMessageRequest.builder();
        deleteRequestCustomizer.getValue().accept(deleteRequestBuilder);
        DeleteMessageRequest deleteRequest = deleteRequestBuilder.build();
        assertThat(deleteRequest.queueUrl()).isEqualTo(QUEUE_URL);
        assertThat(deleteRequest.receiptHandle()).isEqualTo("receipt");
    }
}
