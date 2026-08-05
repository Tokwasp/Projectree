package com.ssafy.projectree.domain.mail.scheduler;

import com.ssafy.projectree.domain.mail.service.InvitationMailSweeper;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "app.invitation-mail.scheduling-enabled",
        havingValue = "true"
)
public class InvitationMailScheduler {

    private final InvitationMailSweeper invitationMailSweeper;

    @Scheduled(fixedDelay = 30_000)
    public void sweep() {
        invitationMailSweeper.sweep();
    }
}
