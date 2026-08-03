package com.ssafy.projectree.domain.mail.service;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import lombok.RequiredArgsConstructor;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class InvitationMailClient {

    private final JavaMailSender mailSender;

    public void send(InvitationMailContent content) {
        MimeMessage message = mailSender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(message, false, "UTF-8");
            helper.setTo(content.recipientEmail());
            helper.setSubject("[Projectree] " + content.inviterName() + "님이 '"
                    + content.projectTitle() + "' 프로젝트에 초대했습니다");
            helper.setText(createHtml(content), true);
        } catch (MessagingException e) {
            throw new IllegalStateException("초대 메일을 구성할 수 없습니다.", e);
        }

        mailSender.send(message);
    }

    private String createHtml(InvitationMailContent content) {
        return "<h2>Projectree 프로젝트 초대</h2>"
                + "<p>" + escapeHtml(content.inviterName()) + "님이 <strong>"
                + escapeHtml(content.projectTitle()) + "</strong> 프로젝트에 초대했습니다.</p>"
                + "<p><a href=\"" + escapeHtml(content.inviteLink()) + "\">초대 수락하기</a></p>"
                + "<p>이 링크는 24시간 후 만료됩니다.</p>";
    }

    private String escapeHtml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
