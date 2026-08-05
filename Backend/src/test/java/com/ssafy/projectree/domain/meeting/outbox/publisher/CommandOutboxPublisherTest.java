package com.ssafy.projectree.domain.meeting.outbox.publisher;

import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.sender.MeetingAnalysisCommandSender;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandOutboxClaimService;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishFailureHandler;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishSuccessHandler;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doAnswer;
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

    @Test
    void oneSendFailureDoesNotBlockFollowingCommand() {
        ClaimedCommandOutbox failed = claimed(1, "command-1", "payload-1");
        ClaimedCommandOutbox succeeded = claimed(2, "command-2", "payload-2");
        when(claimService.claimAvailable()).thenReturn(List.of(failed, succeeded));
        doAnswer(invocation -> {
            if ("command-1".equals(invocation.getArgument(0))) {
                throw new IllegalStateException("SQS unavailable");
            }
            return null;
        }).when(sender).send(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyString());

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

    private ClaimedCommandOutbox claimed(int id, String commandId, String payload) {
        return new ClaimedCommandOutbox(id, commandId, payload, "token-" + id, 1);
    }
}
