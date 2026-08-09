package com.ssafy.projectree.domain.member.controller.response;

import com.ssafy.projectree.domain.member.Member;
import lombok.Getter;

@Getter
public class MemberSearchResponse {

    private final int memberId;
    private final String name;
    private final String email;

    private MemberSearchResponse(int memberId, String name, String email) {
        this.memberId = memberId;
        this.name = name;
        this.email = email;
    }

    public static MemberSearchResponse from(Member member) {
        return of(member.getId(), member.getName(), member.getEmail());
    }

    public static MemberSearchResponse of(int memberId, String name, String email) {
        return new MemberSearchResponse(memberId, name, email);
    }
}
