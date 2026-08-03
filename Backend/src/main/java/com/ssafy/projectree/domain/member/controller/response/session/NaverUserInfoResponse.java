package com.ssafy.projectree.domain.member.controller.response.session;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.ssafy.projectree.domain.member.Member;
import lombok.Builder;
import lombok.Getter;

@Getter
@JsonIgnoreProperties(ignoreUnknown = true)
public class NaverUserInfoResponse {

    private static final String RESULT_CODE_SUCCESS = "00";

    private final String resultCode;
    private final String message;
    private final NaverProfile profile;

    @Builder
    @JsonCreator
    private NaverUserInfoResponse(
            @JsonProperty("resultcode") String resultCode,
            @JsonProperty("message") String message,
            @JsonProperty("response") NaverProfile profile) {
        this.resultCode = resultCode;
        this.message = message;
        this.profile = profile;
    }

    public boolean isFailed() {
        return !RESULT_CODE_SUCCESS.equals(resultCode);
    }

    // 이메일은 네이버의 선택 동의 항목이라 비어 있을 수 있다.
    public boolean hasNoEmail() {
        return profile == null || profile.getEmail() == null || profile.getEmail().isBlank();
    }

    public String getEmail() {
        return profile.getEmail();
    }

    public Member toMember() {
        return Member.builder()
                .email(profile.getEmail())
                .name(profile.getName())
                .build();
    }

    @Getter
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class NaverProfile {

        private final String id;
        private final String email;
        private final String name;
        private final String nickname;
        private final String profileImage;

        @Builder
        @JsonCreator
        private NaverProfile(
                @JsonProperty("id") String id,
                @JsonProperty("email") String email,
                @JsonProperty("name") String name,
                @JsonProperty("nickname") String nickname,
                @JsonProperty("profile_image") String profileImage) {
            this.id = id;
            this.email = email;
            this.name = name;
            this.nickname = nickname;
            this.profileImage = profileImage;
        }
    }
}
