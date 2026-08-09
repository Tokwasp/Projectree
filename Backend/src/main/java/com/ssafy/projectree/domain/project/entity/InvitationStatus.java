package com.ssafy.projectree.domain.project.entity;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public enum InvitationStatus {
    PENDING("수락 대기"),
    ACCEPTED("수락됨"),
    REJECTED("거절됨"),
    CANCELED("취소됨");

    private final String description;
}
