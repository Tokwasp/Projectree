package com.ssafy.projectree.domain.project.controller.dto.response;

import lombok.Getter;

import java.util.List;

@Getter
public class InviteResultsResponse {

    private final List<InviteTargetResponse> results;

    private InviteResultsResponse(List<InviteTargetResponse> results) {
        this.results = results;
    }

    public static InviteResultsResponse from(List<InviteTargetResponse> results) {
        return new InviteResultsResponse(results);
    }
}
