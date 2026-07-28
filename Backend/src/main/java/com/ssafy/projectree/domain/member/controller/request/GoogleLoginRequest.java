package com.ssafy.projectree.domain.member.controller.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Builder;
import lombok.Getter;

@Getter
public class GoogleLoginRequest {

    @NotBlank(message = "인가 코드는 필수입니다.")
    private String code;

    @NotBlank(message = "리다이렉트 URI는 필수입니다.")
    private String redirectUri;

    private GoogleLoginRequest() {
    }

    @Builder
    private GoogleLoginRequest(String code, String redirectUri) {
        this.code = code;
        this.redirectUri = redirectUri;
    }
}
