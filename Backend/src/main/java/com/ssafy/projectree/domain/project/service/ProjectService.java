package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import com.ssafy.projectree.domain.meetingreview.dto.response.MyMeetingReviewResponse;
import com.ssafy.projectree.domain.meetingreview.dto.response.PersonalSpeakingResponse;
import com.ssafy.projectree.domain.meetingreview.exception.MeetingReviewErrorCode;
import com.ssafy.projectree.domain.meetingreview.repository.MeetingReviewRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.controller.dto.response.ProjectHomeResponse;
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
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {

    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingReviewRepository meetingReviewRepository;

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

    public ProjectHomeResponse getProjectHome(Pageable pageable, int projectId, int memberId) {
        if (isNotProjectMember(projectId, memberId)) {
            throw new CustomException(MeetingReviewErrorCode.IS_NOT_PROJECT_MEMBER);
        }

        List<MeetingReview> lastMeetingReviews = meetingReviewRepository.getLastReview(projectId, memberId)
                .map(MeetingReview::getRoomName)
                .map(meetingReviewRepository::findAllByRoomName)
                .orElseGet(List::of);

        if (lastMeetingReviews.isEmpty()) {
            return ProjectHomeResponse.empty();
        }

        MeetingReview myMeetingReview = lastMeetingReviews.stream()
                .filter(mr -> mr.getMemberId() == memberId)
                .findFirst()
                .get();

        List<PersonalSpeakingResponse> speakingResponses = personalSpeakPercentBy(lastMeetingReviews);
        MyMeetingReviewResponse myReviewResponse = MyMeetingReviewResponse.of(myMeetingReview);
        return ProjectHomeResponse.of(null, speakingResponses, myReviewResponse);
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

    private boolean isNotProjectMember(int projectId, int memberId) {
        return !projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId);
    }

    private double toPercent(int speakingSeconds, int totalSpeakTime) {
        if (speakingSeconds == 0 || totalSpeakTime == 0) return 0.0;
        return Math.round(speakingSeconds * 1000.0 / totalSpeakTime) / 10.0;
    }

    private List<PersonalSpeakingResponse> personalSpeakPercentBy(List<MeetingReview> meetingReviews) {
        List<Integer> memberIds = meetingReviews.stream()
                .map(MeetingReview::getMemberId)
                .toList();

        Map<Integer, String> memberIdNameMap = memberRepository.findAllById(memberIds).stream()
                .collect(Collectors.toMap(Member::getId, Member::getName));

        int totalSpeakTime = meetingReviews.stream()
                .mapToInt(MeetingReview::getSpeakingSeconds)
                .sum();

        return meetingReviews.stream()
                .map(review -> PersonalSpeakingResponse.of(
                        memberIdNameMap.get(review.getMemberId()),
                        toPercent(review.getSpeakingSeconds(), totalSpeakTime)))
                .toList();
    }
}
