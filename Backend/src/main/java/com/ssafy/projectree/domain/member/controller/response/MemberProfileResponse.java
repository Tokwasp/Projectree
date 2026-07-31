package com.ssafy.projectree.domain.member.controller.response;

import com.ssafy.projectree.domain.member.Member;
import lombok.Getter;

@Getter
public class MemberProfileResponse {

    private final int memberId;
    private final String name;
    private final String email;

    private MemberProfileResponse(int memberId, String name, String email) {
        this.memberId = memberId;
        this.name = name;
        this.email = email;
    }

    public static MemberProfileResponse from(Member member) {
        return of(member.getId(), member.getName(), member.getEmail());
    }

    public static MemberProfileResponse of(int memberId, String name, String email) {
        return new MemberProfileResponse(memberId, name, email);
    }
}
