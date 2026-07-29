package com.ssafy.projectree.domain.member.controller.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Builder;
import lombok.Getter;

@Getter
public class NaverLoginRequest {

    @NotBlank(message = "인가 코드는 필수입니다.")
    private String code;

    @NotBlank(message = "state는 필수입니다.")
    private String state;

    private NaverLoginRequest() {
    }

    @Builder
    private NaverLoginRequest(String code, String state) {
        this.code = code;
        this.state = state;
    }
}
