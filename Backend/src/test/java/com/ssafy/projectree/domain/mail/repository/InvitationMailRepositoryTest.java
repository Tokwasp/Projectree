package com.ssafy.projectree.domain.mail.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class InvitationMailRepositoryTest extends IntegrationTestSupport {

    private static final LocalDateTime EARLIER_UPDATED_AT = LocalDateTime.of(2026, 7, 30, 10, 0);
    private static final LocalDateTime CUTOFF = LocalDateTime.of(2026, 7, 30, 10, 5);
    private static final LocalDateTime LATER_UPDATED_AT = LocalDateTime.of(2026, 7, 30, 10, 10);

    @Autowired
    private InvitationMailRepository invitationMailRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("발송 대기 메일을 id 오름차순으로 조회하고 페이지 크기만큼만 반환한다.")
    @Test
    void findAllBySendStatusOrderByIdAsc() {
        // given
        InvitationMail firstPendingMail = invitationMailRepository.saveAndFlush(createMail(1));
        InvitationMail secondPendingMail = invitationMailRepository.saveAndFlush(createMail(2));
        InvitationMail requestingMail = createMail(3);
        requestingMail.beginAttempt(LocalDateTime.now());
        invitationMailRepository.saveAndFlush(requestingMail);

        // when
        List<InvitationMail> found = invitationMailRepository.findAllBySendStatusOrderByIdAsc(
                MailSendStatus.NOT_REQUESTED,
                PageRequest.of(0, 1)
        );

        // then
        assertThat(found).containsExactly(firstPendingMail);
        assertThat(found).doesNotContain(secondPendingMail, requestingMail);
    }

    @DisplayName("cutoff 이전에 갱신된 발송 중 메일만 조회한다.")
    @Test
    void findAllBySendStatusAndUpdatedAtBefore() {
        // given
        InvitationMail earlierRequestingMail = saveRequestingMail(1);
        InvitationMail laterRequestingMail = saveRequestingMail(2);
        InvitationMail pendingMail = invitationMailRepository.saveAndFlush(createMail(3));
        updateUpdatedAt(earlierRequestingMail.getId(), EARLIER_UPDATED_AT);
        updateUpdatedAt(laterRequestingMail.getId(), LATER_UPDATED_AT);
        updateUpdatedAt(pendingMail.getId(), EARLIER_UPDATED_AT);
        entityManager.clear();

        // when
        List<InvitationMail> foundBeforeCutoff = invitationMailRepository.findAllBySendStatusAndUpdatedAtBefore(
                MailSendStatus.REQUESTING,
                CUTOFF
        );
        List<InvitationMail> foundAtCutoff = invitationMailRepository.findAllBySendStatusAndUpdatedAtBefore(
                MailSendStatus.REQUESTING,
                EARLIER_UPDATED_AT
        );

        // then
        assertThat(foundBeforeCutoff)
                .extracting(InvitationMail::getId)
                .containsExactly(earlierRequestingMail.getId());
        assertThat(foundAtCutoff).isEmpty();
    }

    private InvitationMail saveRequestingMail(int invitationId) {
        InvitationMail mail = createMail(invitationId);
        mail.beginAttempt(EARLIER_UPDATED_AT);
        return invitationMailRepository.saveAndFlush(mail);
    }

    private void updateUpdatedAt(long id, LocalDateTime updatedAt) {
        entityManager.createNativeQuery("update project_invitation_mail set updated_at = :updatedAt where id = :id")
                .setParameter("updatedAt", updatedAt)
                .setParameter("id", id)
                .executeUpdate();
    }

    private InvitationMail createMail(int invitationId) {
        return InvitationMail.queue(
                invitationId,
                "invitee" + invitationId + "@example.com",
                "https://projectree.site/invitations/token-" + invitationId
        );
    }
}
