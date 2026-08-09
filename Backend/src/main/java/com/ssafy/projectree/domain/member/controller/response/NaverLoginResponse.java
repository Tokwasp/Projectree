package com.ssafy.projectree.domain.member.controller.response;

import com.ssafy.projectree.domain.member.Member;
import lombok.Getter;

@Getter
public class NaverLoginResponse {

    private static final String EMPTY_IMAGE_URL = "";

    private final String name;
    private final String email;
    private final String imageUrl;

    private NaverLoginResponse(String name, String email, String imageUrl) {
        this.name = name;
        this.email = email;
        this.imageUrl = imageUrl;
    }

    public static NaverLoginResponse from(Member member) {
        return new NaverLoginResponse(member.getName(), member.getEmail(), EMPTY_IMAGE_URL);
    }
}
