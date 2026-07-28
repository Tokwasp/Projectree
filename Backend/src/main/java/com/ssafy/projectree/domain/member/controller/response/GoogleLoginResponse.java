package com.ssafy.projectree.domain.member.controller.response;

import com.ssafy.projectree.domain.member.Member;
import lombok.Getter;

@Getter
public class GoogleLoginResponse {

    private static final String EMPTY_IMAGE_URL = "";

    private final String name;
    private final String imageUrl;

    private GoogleLoginResponse(String name, String imageUrl) {
        this.name = name;
        this.imageUrl = imageUrl;
    }

    public static GoogleLoginResponse from(Member member) {
        return new GoogleLoginResponse(member.getName(), EMPTY_IMAGE_URL);
    }
}
