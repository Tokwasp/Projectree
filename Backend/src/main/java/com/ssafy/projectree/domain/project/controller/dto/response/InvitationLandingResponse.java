package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import lombok.Getter;

import java.time.LocalDateTime;

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

    public static InvitationLandingResponse of(
            ProjectInvitation invitation,
            String inviterName,
            LocalDateTime now
    ) {
        return new InvitationLandingResponse(
                invitation.getProject().getTitle(),
                inviterName,
                invitation.getStatus(),
                invitation.isExpired(now)
        );
    }
}
