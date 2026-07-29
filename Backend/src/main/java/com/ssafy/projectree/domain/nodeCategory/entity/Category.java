package com.ssafy.projectree.domain.nodeCategory.entity;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
public enum Category {
    Frontend("프론트엔드"),
    Backend("백엔드"),
    AI("AI"),
    Infra("Infra"),
    Design("디자인"),
    Planning("기획");

    private final String description;
}
