package com.ssafy.projectree.domain.project.event;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.notification.repository.NotificationRepository;
import com.ssafy.projectree.domain.notification.service.NotificationPublisher;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ProjectInvitationReceivedNotificationTransactionTest
        extends IntegrationTestSupport {

    @Autowired
    private ApplicationEventPublisher applicationEventPublisher;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private NotificationRepository notificationRepository;

    @MockitoBean
    private NotificationPublisher notificationPublisher;

    @AfterEach
    void cleanUp() {
        notificationRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @Test
    void doesNotCreateNotificationWhenInvitationTransactionRollsBack() {
        Member invitee = memberRepository.saveAndFlush(Member.builder()
                .email("rollback-invitee@example.com")
                .name("초대 대상")
                .build());
        TransactionTemplate transactionTemplate =
                new TransactionTemplate(transactionManager);

        transactionTemplate.executeWithoutResult(status -> {
            applicationEventPublisher.publishEvent(
                    new ProjectInvitationReceivedNotificationEvent(invitee.getId())
            );
            status.setRollbackOnly();
        });

        assertThat(notificationRepository.findAll()).isEmpty();
        verifyNoInteractions(notificationPublisher);
    }
}
