package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.project.exception.ProjectErrorCode;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.domain.project.service.result.MemberInviteResult;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
@Slf4j
@RequiredArgsConstructor
public class ProjectInvitationService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectInvitationProcessor projectInvitationProcessor;

    public List<MemberInviteResult> invite(
            int projectId,
            int inviterMemberId,
            List<Integer> inviteeMemberIds
    ) {
        validateProjectAndOwner(projectId, inviterMemberId);

        List<MemberInviteResult> results = new ArrayList<>();
        for (int inviteeMemberId : inviteeMemberIds) {
            results.add(processInvite(projectId, inviterMemberId, inviteeMemberId));
        }
        return results;
    }

    private void validateProjectAndOwner(int projectId, int inviterMemberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                projectId, inviterMemberId, ProjectRole.OWNER
        )) {
            throw new CustomException(ProjectErrorCode.NOT_PROJECT_OWNER);
        }
    }

    private MemberInviteResult processInvite(int projectId, int inviterMemberId, int inviteeMemberId) {
        try {
            return projectInvitationProcessor.processInvite(projectId, inviterMemberId, inviteeMemberId);
        } catch (DataIntegrityViolationException e) {
            // 동시 초대로 유니크 제약에 걸린 대상은 방금 생성된 초대와 같은 쿨다운으로 처리한다.
            log.warn("초대 저장 중 무결성 위반, COOLDOWN으로 처리: {}", e.getMessage());
            return new MemberInviteResult(inviteeMemberId, InviteResult.COOLDOWN);
        }
    }
}
