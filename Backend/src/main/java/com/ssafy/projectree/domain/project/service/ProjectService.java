package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.BusinessException;
import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;

    @Transactional
    public int createProject(ProjectCreateRequest dto, int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new BusinessException(ErrorCode.MEMBER_NOT_FOUND);
        }

        // 프로젝트 객체 생성
        Project project = Project.builder()
                .title(dto.getTitle())
                .content(dto.getContent())
                .photoUrl(dto.getPhotoUrl())
                .build();

        // 프로젝트 멤버 객체 생성
        ProjectMember pm = ProjectMember.builder()
                .memberId(memberId)
                .role(ProjectRole.OWNER)
                .build();

        project.addMember(pm);
        return projectRepository.save(project).getId();
    }
}
