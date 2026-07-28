package com.ssafy.projectree.domain.member.controller.response.session;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.ssafy.projectree.domain.member.Member;
import lombok.Builder;
import lombok.Getter;

@Getter
@JsonIgnoreProperties(ignoreUnknown = true)
public class GoogleUserInfoResponse {

    private final String sub;
    private final String email;
    private final boolean emailVerified;
    private final String name;
    private final String picture;

    @Builder
    @JsonCreator
    private GoogleUserInfoResponse(
            @JsonProperty("sub") String sub,
            @JsonProperty("email") String email,
            @JsonProperty("email_verified") boolean emailVerified,
            @JsonProperty("name") String name,
            @JsonProperty("picture") String picture) {
        this.sub = sub;
        this.email = email;
        this.emailVerified = emailVerified;
        this.name = name;
        this.picture = picture;
    }

    public Member toMember() {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }
}
