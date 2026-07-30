package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.project.service.result.MemberInviteResult;
import lombok.Getter;

import java.util.List;

@Getter
public class InviteResultsResponse {

    private final List<MemberInviteResult> results;

    private InviteResultsResponse(List<MemberInviteResult> results) {
        this.results = results;
    }

    public static InviteResultsResponse from(List<MemberInviteResult> results) {
        return new InviteResultsResponse(results);
    }
}
