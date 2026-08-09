package com.ssafy.projectree.domain.mail.entity;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public enum MailSendStatus {
    NOT_REQUESTED("발송 대기"),
    REQUESTING("발송 중"),
    SENT("발송 완료"),
    FAILED("발송 실패 확정");

    private final String description;
}
