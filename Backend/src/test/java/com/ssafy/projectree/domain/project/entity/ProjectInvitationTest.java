package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.domain.project.exception.InvitationErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectInvitationTest {

    private static final LocalDateTime INVITED_AT = LocalDateTime.of(2026, 7, 30, 10, 0);

    @DisplayName("초대를 생성하면 PENDING 상태와 24시간 뒤 만료 시각으로 초기화된다.")
    @Test
    void build_initializesPendingInvitation() {
        // given & when
        ProjectInvitation invitation = createInvitation(INVITED_AT);

        // then
        assertThat(invitation.getStatus()).isEqualTo(InvitationStatus.PENDING);
        assertThat(invitation.getExpiresAt()).isEqualTo(INVITED_AT.plusHours(24));
        assertThat(invitation.getAcceptedAt()).isNull();
        assertThat(invitation.getRejectedAt()).isNull();
        assertThat(invitation.getCanceledAt()).isNull();
    }

    @DisplayName("자기 자신을 초대하면 예외가 발생한다.")
    @Test
    void build_withSameInviterAndInvitee_throwsException() {
        // given & when & then
        assertThatThrownBy(() -> ProjectInvitation.builder()
                .project(createProject())
                .inviterMemberId(1)
                .inviteeMemberId(1)
                .tokenHash("token-hash")
                .lastInvitedAt(INVITED_AT)
                .build())
                .isInstanceOf(IllegalArgumentException.class);
    }

    @DisplayName("수락, 거절, 취소하면 각각 상태와 처리 시각이 기록된다.")
    @Test
    void changesStatusAndRecordsProcessedAt() {
        // given
        LocalDateTime processedAt = INVITED_AT.plusMinutes(10);
        ProjectInvitation acceptedInvitation = createInvitation(INVITED_AT);
        ProjectInvitation rejectedInvitation = createInvitation(INVITED_AT);
        ProjectInvitation canceledInvitation = createInvitation(INVITED_AT);

        // when
        acceptedInvitation.accept(processedAt);
        rejectedInvitation.reject(processedAt);
        canceledInvitation.cancel(processedAt);

        // then
        assertThat(acceptedInvitation.getStatus()).isEqualTo(InvitationStatus.ACCEPTED);
        assertThat(acceptedInvitation.getAcceptedAt()).isEqualTo(processedAt);
        assertThat(rejectedInvitation.getStatus()).isEqualTo(InvitationStatus.REJECTED);
        assertThat(rejectedInvitation.getRejectedAt()).isEqualTo(processedAt);
        assertThat(canceledInvitation.getStatus()).isEqualTo(InvitationStatus.CANCELED);
        assertThat(canceledInvitation.getCanceledAt()).isEqualTo(processedAt);
    }

    @DisplayName("대기 상태가 아닌 초대를 수락하면 INVITATION_NOT_PENDING 예외가 발생한다.")
    @Test
    void accept_nonPendingInvitation_throwsException() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);
        invitation.cancel(INVITED_AT.plusMinutes(1));

        // when & then
        assertThatThrownBy(() -> invitation.accept(INVITED_AT.plusMinutes(2)))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(InvitationErrorCode.INVITATION_NOT_PENDING);
    }

    @DisplayName("만료 시각과 같은 시각부터 초대는 만료되며 수락할 수 없다.")
    @Test
    void accept_expiredInvitation_throwsException() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);
        LocalDateTime expiresAt = invitation.getExpiresAt();

        // when & then
        assertThat(invitation.isExpired(expiresAt)).isTrue();
        assertThatThrownBy(() -> invitation.accept(expiresAt))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(InvitationErrorCode.INVITATION_EXPIRED);
    }

    @DisplayName("만료된 초대를 거절하면 INVITATION_EXPIRED 예외가 발생한다.")
    @Test
    void reject_expiredInvitation_throwsException() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);
        LocalDateTime expiresAt = invitation.getExpiresAt();

        // when & then
        assertThatThrownBy(() -> invitation.reject(expiresAt))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(InvitationErrorCode.INVITATION_EXPIRED);
    }

    @DisplayName("만료된 초대도 소유자가 취소할 수 있다.")
    @Test
    void cancel_expiredInvitation() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);

        // when
        invitation.cancel(invitation.getExpiresAt());

        // then
        assertThat(invitation.getStatus()).isEqualTo(InvitationStatus.CANCELED);
    }

    @DisplayName("종료된 초대를 재초대하면 PENDING으로 돌아가고 처리 시각이 초기화된다.")
    @Test
    void reinvite_resetsInvitation() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);
        invitation.accept(INVITED_AT.plusMinutes(1));
        LocalDateTime reinvitedAt = INVITED_AT.plusDays(1);

        // when
        invitation.reinvite("new-token-hash", reinvitedAt);

        // then
        assertThat(invitation.getStatus()).isEqualTo(InvitationStatus.PENDING);
        assertThat(invitation.getTokenHash()).isEqualTo("new-token-hash");
        assertThat(invitation.getLastInvitedAt()).isEqualTo(reinvitedAt);
        assertThat(invitation.getExpiresAt()).isEqualTo(reinvitedAt.plusHours(24));
        assertThat(invitation.getAcceptedAt()).isNull();
        assertThat(invitation.getRejectedAt()).isNull();
        assertThat(invitation.getCanceledAt()).isNull();
    }

    @DisplayName("대기 중인 초대를 재초대하면 예외가 발생한다.")
    @Test
    void reinvite_pendingInvitation_throwsException() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);

        // when & then
        assertThatThrownBy(() -> invitation.reinvite("new-token-hash", INVITED_AT.plusMinutes(1)))
                .isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("재발송하면 토큰과 만료 시각이 갱신되고 60초 경계부터 재발송이 가능하다.")
    @Test
    void resend_renewsInvitationAndChecksCooldownBoundary() {
        // given
        ProjectInvitation invitation = createInvitation(INVITED_AT);
        LocalDateTime resentAt = INVITED_AT.plusSeconds(60);

        // when
        invitation.resend("new-token-hash", resentAt);

        // then
        assertThat(invitation.getTokenHash()).isEqualTo("new-token-hash");
        assertThat(invitation.getExpiresAt()).isEqualTo(resentAt.plusHours(24));
        assertThat(invitation.isResendCoolingDown(resentAt.plusSeconds(59))).isTrue();
        assertThat(invitation.isResendCoolingDown(resentAt.plusSeconds(60))).isFalse();
    }

    private ProjectInvitation createInvitation(LocalDateTime invitedAt) {
        return ProjectInvitation.builder()
                .project(createProject())
                .inviterMemberId(1)
                .inviteeMemberId(2)
                .tokenHash("token-hash")
                .lastInvitedAt(invitedAt)
                .build();
    }

    private Project createProject() {
        return Project.builder()
                .title("포트폴리오 사이트")
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
    }
}
