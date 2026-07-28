package com.ssafy.projectree.domain.member;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Getter;

@Getter
public class LoginMember {

    private final Integer id;
    private final String name;
    private final String email;

    @Builder
    @JsonCreator
    private LoginMember(
            @JsonProperty("id") Integer id,
            @JsonProperty("name") String name,
            @JsonProperty("email") String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public static LoginMember from(Member member) {
        return new LoginMember(member.getId(), member.getName(), member.getEmail());
    }
}
