package com.ssafy.projectree.domain.project.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum InvitationErrorCode implements ErrorCode {
    INVITATION_NOT_FOUND(HttpStatus.NOT_FOUND, "유효하지 않은 초대입니다."),
    INVITATION_NOT_PENDING(HttpStatus.CONFLICT, "이미 처리된 초대입니다."),
    INVITATION_EXPIRED(HttpStatus.GONE, "만료된 초대입니다."),
    INVITATION_INVITEE_MISMATCH(HttpStatus.FORBIDDEN, "초대 대상이 아닙니다.");

    private final HttpStatus status;
    private final String message;
}
