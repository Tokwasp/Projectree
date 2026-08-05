package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.config.AnalysisResultConsumerProperties;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;

import java.util.List;

public class AnalysisResultSqsGateway implements AutoCloseable {

    private final SqsClient sqsClient;
    private final AnalysisResultConsumerProperties properties;

    public AnalysisResultSqsGateway(
            SqsClient sqsClient,
            AnalysisResultConsumerProperties properties
    ) {
        this.sqsClient = sqsClient;
        this.properties = properties;
    }

    public List<Message> receiveMessages() {
        return sqsClient.receiveMessage(ReceiveMessageRequest.builder()
                        .queueUrl(properties.queueUrl())
                        .waitTimeSeconds(properties.waitTimeSeconds())
                        .maxNumberOfMessages(properties.maxNumberOfMessages())
                        .messageSystemAttributeNames(MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT)
                        .build())
                .messages();
    }

    public void deleteMessage(Message message) {
        sqsClient.deleteMessage(request -> request
                .queueUrl(properties.queueUrl())
                .receiptHandle(message.receiptHandle()));
    }

    @Override
    public void close() {
        sqsClient.close();
    }
}
