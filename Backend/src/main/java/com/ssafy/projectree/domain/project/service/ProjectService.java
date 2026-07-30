package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.nodeCategory.entity.Category;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectCategory;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;

    @Transactional
    public int createProject(ProjectCreateRequest request, int memberId) {
        validateMember(memberId);

        Project project = request.toEntity();
        ProjectMember pm = ProjectMember.createMember(memberId, ProjectRole.OWNER);

        addCategories(project, request);
        project.addMember(pm);

        return projectRepository.save(project).getId();
    }

    @Transactional
    public void deleteProject(int projectId, int memberId) {
        Project project = findProject(projectId);

        if (project.isNotOwner(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
        }

        projectRepository.delete(project);
    }

    @Transactional
    public void leaveProject(int projectId, int memberId) {
        Project project = findProject(projectId);

        if (project.isNotParticipant(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }

        if (project.isOwner(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_LEAVE_FORBIDDEN);
        }

        project.removeMember(memberId);
    }

    public List<ProjectMemberResponse> getProjectMembers(int projectId, int memberId) {
        Project project = findProject(projectId);

        if (project.isNotParticipant(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }

        return projectMemberRepository.findMemberResponsesByProjectId(projectId);
    }

    private void validateMember(int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new CustomException(ProjectErrorCode.MEMBER_NOT_FOUND);
        }
    }

    private static void addCategories(Project project, ProjectCreateRequest request) {
        Set<Integer> categoryIds = new HashSet<>(request.getCategoryIds());

        for (int categoryId : categoryIds) {
            if (Category.isNotValid(categoryId)) {
                throw new CustomException(ProjectErrorCode.INVALID_CATEGORY);
            }

            ProjectCategory pc = ProjectCategory.createProjectCategory(categoryId);
            project.addCategory(pc);
        }
    }

    private Project findProject(int projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() ->
                        new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
    }
}
