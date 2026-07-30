package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import com.ssafy.projectree.domain.project.service.result.InvitationLanding;
import lombok.Getter;

@Getter
public class InvitationLandingResponse {

    private final String projectTitle;
    private final String inviterName;
    private final InvitationStatus status;
    private final boolean expired;

    private InvitationLandingResponse(
            String projectTitle,
            String inviterName,
            InvitationStatus status,
            boolean expired
    ) {
        this.projectTitle = projectTitle;
        this.inviterName = inviterName;
        this.status = status;
        this.expired = expired;
    }

    public static InvitationLandingResponse from(InvitationLanding landing) {
        return new InvitationLandingResponse(
                landing.projectTitle(),
                landing.inviterName(),
                landing.status(),
                landing.expired()
        );
    }
}
