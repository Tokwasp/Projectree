package com.ssafy.projectree.domain.member.controller.response;

import com.ssafy.projectree.domain.member.Member;
import lombok.Getter;

@Getter
public class MemberProfileResponse {

    private final int memberId;
    private final String name;
    private final String email;
    private final String profileImageUrl;

    private MemberProfileResponse(int memberId, String name, String email, String profileImageUrl) {
        this.memberId = memberId;
        this.name = name;
        this.email = email;
        this.profileImageUrl = profileImageUrl;
    }

    public static MemberProfileResponse from(Member member) {
        return of(
                member.getId(),
                member.getName(),
                member.getEmail(),
                member.getProfileImageUrl()
        );
    }

    public static MemberProfileResponse of(int memberId, String name, String email) {
        return of(memberId, name, email, null);
    }

    public static MemberProfileResponse of(
            int memberId, String name, String email, String profileImageUrl
    ) {
        return new MemberProfileResponse(memberId, name, email, profileImageUrl);
    }
}
