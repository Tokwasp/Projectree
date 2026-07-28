package com.ssafy.projectree.domain.response;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Getter;

@Getter
@JsonIgnoreProperties(ignoreUnknown = true)
public class GoogleTokenResponse {

    private final String accessToken;
    private final String idToken;
    private final String tokenType;
    private final Long expiresIn;

    @Builder
    @JsonCreator
    private GoogleTokenResponse(
            @JsonProperty("access_token") String accessToken,
            @JsonProperty("id_token") String idToken,
            @JsonProperty("token_type") String tokenType,
            @JsonProperty("expires_in") Long expiresIn) {
        this.accessToken = accessToken;
        this.idToken = idToken;
        this.tokenType = tokenType;
        this.expiresIn = expiresIn;
    }
}
