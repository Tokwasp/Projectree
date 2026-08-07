package com.ssafy.projectree.domain.meeting.outbox.publisher;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.sender.CommandSendResult;
import com.ssafy.projectree.domain.meeting.outbox.sender.MeetingAnalysisCommandSender;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandOutboxClaimService;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishFailureHandler;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishSuccessHandler;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CommandOutboxPublisherTest {

    private final CommandOutboxClaimService claimService = mock(CommandOutboxClaimService.class);
    private final MeetingAnalysisCommandSender sender = mock(MeetingAnalysisCommandSender.class);
    private final CommandPublishSuccessHandler successHandler = mock(CommandPublishSuccessHandler.class);
    private final CommandPublishFailureHandler failureHandler = mock(CommandPublishFailureHandler.class);
    private final CommandOutboxPublisher publisher = new CommandOutboxPublisher(
            claimService, sender, successHandler, failureHandler
    );
    private Logger logger;
    private ListAppender<ILoggingEvent> logAppender;

    @BeforeEach
    void setUpLogCapture() {
        logger = (Logger) LoggerFactory.getLogger(CommandOutboxPublisher.class);
        logAppender = new ListAppender<>();
        logAppender.start();
        logger.addAppender(logAppender);
    }

    @AfterEach
    void tearDownLogCapture() {
        logger.detachAppender(logAppender);
        logAppender.stop();
    }

    @Test
    void oneSendFailureDoesNotBlockFollowingCommand() {
        ClaimedCommandOutbox failed = claimed(1, "command-1", "payload-1");
        ClaimedCommandOutbox succeeded = claimed(2, "command-2", "payload-2");
        when(claimService.claimAvailable()).thenReturn(List.of(failed, succeeded));
        when(sender.send(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString()
        )).thenAnswer(invocation -> {
            if ("command-1".equals(invocation.getArgument(0))) {
                throw new IllegalStateException("SQS unavailable");
            }
            return new CommandSendResult("message-2");
        });

        publisher.publishAvailable();

        verify(failureHandler).handle(
                org.mockito.ArgumentMatchers.eq(failed),
                org.mockito.ArgumentMatchers.any(IllegalStateException.class)
        );
        verify(sender).send("command-2", "payload-2");
        verify(successHandler).handle(succeeded);
    }

    @Test
    void claimFailureAbortsCurrentCycle() {
        RuntimeException failure = new RuntimeException("claim failed");
        when(claimService.claimAvailable()).thenThrow(failure);

        assertThatThrownBy(publisher::publishAvailable).isSameAs(failure);

        verify(sender, never()).send(
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString()
        );
    }

    @Test
    void publishedLogIdentifiesMeetingAnalysisCommandWithoutPayload() {
        assertPublishedLogCommandType(MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED);
    }

    @Test
    void publishedLogIdentifiesNodeContentUpdateCommandWithoutPayload() {
        assertPublishedLogCommandType(MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED);
    }

    private void assertPublishedLogCommandType(MeetingAnalysisCommandType commandType) {
        ClaimedCommandOutbox claimed = new ClaimedCommandOutbox(
                31,
                "command-31",
                commandType,
                "SENSITIVE_COMMAND_PAYLOAD",
                "token-31",
                1
        );
        when(claimService.claimAvailable()).thenReturn(List.of(claimed));
        when(sender.send("command-31", "SENSITIVE_COMMAND_PAYLOAD"))
                .thenReturn(new CommandSendResult("message-31"));

        publisher.publishAvailable();

        assertThat(publishedLogs()).singleElement().satisfies(message -> assertThat(message)
                .contains("commandId=command-31")
                .contains("commandType=" + commandType)
                .contains("outboxId=31")
                .contains("sqsMessageId=message-31")
                .contains("attemptCount=1")
                .doesNotContain("SENSITIVE_COMMAND_PAYLOAD"));
        verify(successHandler).handle(claimed);
    }

    private List<String> publishedLogs() {
        return logAppender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .filter(message -> message.contains("COMMAND_SQS_PUBLISHED"))
                .toList();
    }

    private ClaimedCommandOutbox claimed(int id, String commandId, String payload) {
        return new ClaimedCommandOutbox(id, commandId, payload, "token-" + id, 1);
    }
}
