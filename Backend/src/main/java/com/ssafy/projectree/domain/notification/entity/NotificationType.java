package com.ssafy.projectree.domain.notification.entity;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public enum NotificationType {

    TREE_CREATED("트리 생성이 완료되었어요."),
    MEETING_RECORD_CREATED("회의록 생성이 완료되었어요.");

    private final String message;
}
