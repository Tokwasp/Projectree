package com.ssafy.projectree.domain.project.controller.dto.request;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.HashSet;
import java.util.List;

@Getter
@NoArgsConstructor
public class InvitationCreateRequest {

    @NotEmpty
    @Size(max = 10)
    private List<Integer> inviteeMemberIds;

    @AssertTrue(message = "초대 대상은 중복될 수 없습니다.")
    public boolean hasNoDuplicateInviteeMemberIds() {
        return inviteeMemberIds == null || inviteeMemberIds.size() == new HashSet<>(inviteeMemberIds).size();
    }
}
