package com.ssafy.projectree.domain.project.controller.dto.response;

import lombok.Getter;

@Getter
public class InvitationAcceptResponse {

    private final int projectId;

    private InvitationAcceptResponse(int projectId) {
        this.projectId = projectId;
    }

    public static InvitationAcceptResponse of(int projectId) {
        return new InvitationAcceptResponse(projectId);
    }
}
