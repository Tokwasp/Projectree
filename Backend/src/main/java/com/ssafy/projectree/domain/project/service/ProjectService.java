package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectListResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {
    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingRepository meetingRepository;

    @Transactional
    public int createProject(ProjectCreateRequest request, int memberId) {
        validateMember(memberId);

        Project project = request.toEntity();
        ProjectMember pm = ProjectMember.createMember(memberId, ProjectRole.OWNER);

        project.addMember(pm);

        return projectRepository.save(project).getId();
    }

    @Transactional
    public void deleteProject(int projectId, int memberId) {
        Project project = findProject(projectId);

        if (project.isNotOwner(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
        }
        if (meetingRepository.existsByProjectId(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_HAS_MEETINGS);
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

    public ProjectListResponse getProjectList(Pageable pageable, int memberId) {
        Page<ProjectItemResponse> projectPage =
                projectRepository.findProjectItemsByMemberId(memberId, pageable);

        return new ProjectListResponse(projectPage);
    }

    private void validateMember(int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new CustomException(ProjectErrorCode.MEMBER_NOT_FOUND);
        }
    }

    private Project findProject(int projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() ->
                        new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
    }
}
