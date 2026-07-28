package com.ssafy.projectree.domain.member.controller.response.session;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Getter;

@Getter
@JsonIgnoreProperties(ignoreUnknown = true)
public class NaverTokenResponse {

    private final String accessToken;
    private final String refreshToken;
    private final String tokenType;
    private final Long expiresIn;
    private final String error;
    private final String errorDescription;

    @Builder
    @JsonCreator
    private NaverTokenResponse(
            @JsonProperty("access_token") String accessToken,
            @JsonProperty("refresh_token") String refreshToken,
            @JsonProperty("token_type") String tokenType,
            @JsonProperty("expires_in") Long expiresIn,
            @JsonProperty("error") String error,
            @JsonProperty("error_description") String errorDescription) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        this.tokenType = tokenType;
        this.expiresIn = expiresIn;
        this.error = error;
        this.errorDescription = errorDescription;
    }

    // 네이버는 인증 실패도 HTTP 200으로 응답한다. 상태 코드가 아니라 바디로 판별해야 한다.
    public boolean isFailed() {
        return accessToken == null || accessToken.isBlank();
    }
}
