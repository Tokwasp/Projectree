package com.ssafy.projectree.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
@Getter
public enum Domain {
    MEMBER("멤버"),
    PROJECT("프로젝트"),
    PROJECT_MEMBER("프로젝트 멤버");

    private final String description;


}
