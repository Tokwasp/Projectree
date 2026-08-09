package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.project.service.result.InviteResult;
import lombok.Getter;

@Getter
public class InviteTargetResponse {

    private final int inviteeMemberId;
    private final InviteResult result;

    private InviteTargetResponse(int inviteeMemberId, InviteResult result) {
        this.inviteeMemberId = inviteeMemberId;
        this.result = result;
    }

    public static InviteTargetResponse of(int inviteeMemberId, InviteResult result) {
        return new InviteTargetResponse(inviteeMemberId, result);
    }
}
