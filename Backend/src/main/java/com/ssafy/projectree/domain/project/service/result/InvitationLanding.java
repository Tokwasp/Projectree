package com.ssafy.projectree.domain.project.service.result;

import com.ssafy.projectree.domain.project.entity.InvitationStatus;

public record InvitationLanding(
        String projectTitle,
        String inviterName,
        InvitationStatus status,
        boolean expired
) {
}
