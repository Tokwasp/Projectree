package com.ssafy.projectree.domain.meeting.outbox.config;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.outbox.publisher.CommandOutboxPublisher;
import com.ssafy.projectree.domain.meeting.outbox.scheduler.CommandOutboxPublisherScheduler;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import software.amazon.awssdk.services.sqs.SqsClient;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingAnalysisPublisherDisabledTest extends IntegrationTestSupport {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void disabledPublisherDoesNotCreateAwsOrSchedulerBeans() {
        assertThat(applicationContext.getBeansOfType(SqsClient.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(CommandOutboxPublisher.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(CommandOutboxPublisherScheduler.class)).isEmpty();
    }
}
