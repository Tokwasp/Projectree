package com.ssafy.projectree.domain.meeting.outbox.publisher;

import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.sender.MeetingAnalysisCommandSender;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandOutboxClaimService;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishFailureHandler;
import com.ssafy.projectree.domain.meeting.outbox.service.CommandPublishSuccessHandler;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.publisher",
        name = "enabled",
        havingValue = "true"
)
public class CommandOutboxPublisher {

    private final CommandOutboxClaimService claimService;
    private final MeetingAnalysisCommandSender sender;
    private final CommandPublishSuccessHandler successHandler;
    private final CommandPublishFailureHandler failureHandler;

    public int publishAvailable() {
        List<ClaimedCommandOutbox> claimedCommands = claimService.claimAvailable();
        if (claimedCommands.isEmpty()) {
            log.debug("No meeting analysis commands available for publishing");
            return 0;
        }

        for (ClaimedCommandOutbox claimed : claimedCommands) {
            publishOne(claimed);
        }
        return claimedCommands.size();
    }

    private void publishOne(ClaimedCommandOutbox claimed) {
        try {
            sender.send(claimed.commandId(), claimed.payload());
        } catch (RuntimeException failure) {
            log.warn(
                    "Meeting analysis command publish failed. outboxId={}, attemptCount={}",
                    claimed.outboxId(),
                    claimed.attemptCount()
            );
            try {
                failureHandler.handle(claimed, failure);
            } catch (RuntimeException handlingFailure) {
                log.error(
                        "Meeting analysis publish failure handling failed. outboxId={}",
                        claimed.outboxId(),
                        handlingFailure
                );
            }
            return;
        }

        try {
            successHandler.handle(claimed);
        } catch (RuntimeException successHandlingFailure) {
            // SQS 성공 후 DB 반영 실패 여부는 알 수 없으므로 PUBLISHING lease 만료 복구에 맡긴다.
            log.error(
                    "SQS send succeeded but publish success handling failed. outboxId={}",
                    claimed.outboxId(),
                    successHandlingFailure
            );
        }
    }
}
