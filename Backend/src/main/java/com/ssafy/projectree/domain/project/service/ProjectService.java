package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;

    public int createProject(ProjectCreateRequest request, int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new CustomException(CommonErrorCode.MEMBER_NOT_FOUND);
        }

        Project project = request.toEntity();
        ProjectMember pm = ProjectMember.createMember(memberId, ProjectRole.OWNER);

        project.addMember(pm);
        return projectRepository.save(project).getId();
    }
}
