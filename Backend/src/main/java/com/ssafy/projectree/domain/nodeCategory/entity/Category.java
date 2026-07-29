package com.ssafy.projectree.domain.nodeCategory.entity;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
public enum Category {
    // 선언 순서는 data.sql의 node_category id 순서와 일치해야 한다.
    Frontend("프론트엔드"),
    Backend("백엔드"),
    AI("AI"),
    Infra("Infra"),
    Planning("기획"),
    Design("디자인");

    private final String description;
}
