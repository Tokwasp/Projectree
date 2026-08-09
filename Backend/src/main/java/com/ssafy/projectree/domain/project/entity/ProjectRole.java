package com.ssafy.projectree.domain.project.entity;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
public enum ProjectRole {
    OWNER("프로젝트 생성자"), MEMBER("프로젝트 멤버");

    private final String description;
}
