package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.transaction.Transactional;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;

    @Transactional
    public Integer createProject(@Valid ProjectCreateRequest dto, Integer memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new IllegalArgumentException("존재하지 않는 회원입니다.");
        }

        Project project = Project.builder()
                .title(dto.getTitle())
                .content(dto.getContent())
                .photoUrl(dto.getPhotoUrl())
                .build();

        project.addMember(memberId, ProjectRole.OWNER);
        return projectRepository.save(project).getId();
    }
}
