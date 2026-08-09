package com.ssafy.projectree.domain.nodeCategory.entity;

import lombok.RequiredArgsConstructor;

@RequiredArgsConstructor
public enum Category {
    Frontend("프론트엔드"),
    Backend("백엔드"),
    AI("AI"),
    Infra("Infra"),
    Planning("기획"),
    Design("디자인");

    private final String description;

    public static boolean isValidId(int id) {
        return id >= 1 && id <= values().length;
    }

    public static boolean isNotValid(int id) {
        return !isValidId(id);
    }
}
