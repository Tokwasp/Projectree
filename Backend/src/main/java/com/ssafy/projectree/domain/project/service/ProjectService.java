package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectCategory;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.Set;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;

    @Transactional
    public int createProject(ProjectCreateRequest request, int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new CustomException(ProjectErrorCode.MEMBER_NOT_FOUND);
        }

        Project project = request.toEntity();
        ProjectMember pm = ProjectMember.createMember(memberId, ProjectRole.OWNER);

        Set<Integer> categoryIds = new HashSet<>(request.getCategoryIds());

        for (Integer categoryId : categoryIds) {
            if (categoryId < 1 || categoryId > 6) {
                throw new CustomException(ProjectErrorCode.INVALID_REQUEST);
            }

            ProjectCategory pc = ProjectCategory.createProjectCategory(categoryId);
            project.addCategory(pc);
        }

        project.addMember(pm);

        return projectRepository.save(project).getId();
    }
}
