package com.ssafy.projectree.domain.mail.repository;

import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

public interface InvitationMailRepository extends JpaRepository<InvitationMail, Integer> {

    List<InvitationMail> findAllBySendStatusOrderByIdAsc(MailSendStatus sendStatus, Pageable pageable);

    List<InvitationMail> findAllBySendStatusAndUpdatedAtBefore(MailSendStatus sendStatus, LocalDateTime cutoff);

    List<InvitationMail> findAllByInvitationIdIn(List<Integer> invitationIds);
}
