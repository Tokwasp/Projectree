package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import com.ssafy.projectree.domain.meetingreview.repository.MeetingReviewRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.controller.dto.response.home.MeetingRecordResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.home.MyMeetingReviewResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.home.PersonalSpeakingResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.home.ProjectDetailResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.home.ProjectHomeResponse;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectListResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectMemberErrorCode;
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

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ProjectService {

    // ProjectRepository 의 검색 쿼리에 선언된 escape 문자와 반드시 같아야 한다.
    private static final String LIKE_ESCAPE_CHAR = "!";

    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingReviewRepository meetingReviewRepository;
    private final ProjectGraphSyncRepository projectGraphSyncRepository;
    private final MeetingRecordRepository meetingRecordRepository;
    private final ProjectDeletionService projectDeletionService;

    @Transactional
    public int createProject(ProjectCreateRequest request, int memberId) {
        validateMember(memberId);

        Project project = request.toEntity();
        ProjectMember pm = ProjectMember.createMember(memberId, ProjectRole.OWNER);

        project.addMember(pm);

        Project savedProject = projectRepository.saveAndFlush(project);
        projectGraphSyncRepository.save(
                ProjectGraphSync.initial(savedProject.getId(), Instant.now())
        );
        return savedProject.getId();
    }

    @Transactional
    public void updateImage(int projectId, int memberId, String imageURL) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        if (isNotProjectOwner(projectId, memberId)) {
            throw new CustomException(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
        }
        project.updateImageURL(imageURL);
    }

    @Transactional
    public void updateTitle(int projectId, int memberId, String title) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        if (isNotProjectOwner(projectId, memberId)) {
            throw new CustomException(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
        }
        project.updateTitle(title);
    }

    @Transactional
    public void updateContent(int projectId, int memberId, String content) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        if (isNotProjectOwner(projectId, memberId)) {
            throw new CustomException(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
        }
        project.updateContent(content);
    }

    @Transactional
    public void deleteProject(int projectId, int memberId) {
        Project project = projectRepository.findByIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        if (project.isNotOwner(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
        }

        projectDeletionService.deleteProjectAggregate(projectId);
    }

    @Transactional
    public void leaveProject(int projectId, int memberId) {
        Project project = projectRepository.findByIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        if (project.isNotParticipant(memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }

        if (project.isOwner(memberId)) {
            projectDeletionService.deleteProjectAggregate(projectId);
            return;
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

    public ProjectListResponse getProjectList(Pageable pageable, int memberId, String keyword) {
        Page<ProjectItemResponse> projectPage =
                projectRepository.findProjectItemsByMemberId(memberId, normalizeKeyword(keyword), pageable);

        return new ProjectListResponse(projectPage);
    }

    public ProjectHomeResponse getProjectHome(int projectId, int memberId) {
        checkingValidate(projectId, memberId);

        ProjectDetailResponse projectDetail = getProjectDetail(projectId);
        List<MeetingRecordResponse> meetingRecords = getRecentFiveMeetingRecord(projectId);
        List<MeetingReview> recentOneMeetingReviews = getRecentOneMeetingReviews(projectId, memberId);

        if (isRecentReviewNotExist(recentOneMeetingReviews)) {
            return ProjectHomeResponse.notExistRecentReview(projectDetail, meetingRecords);
        }

        MeetingReview myMeetingReview = findMyReviewOf(recentOneMeetingReviews, memberId);
        List<PersonalSpeakingResponse> speakingResponses = calculatePersonalSpeakPercentBy(recentOneMeetingReviews);
        MyMeetingReviewResponse myReviewResponse = MyMeetingReviewResponse.of(myMeetingReview);
        return ProjectHomeResponse.of(projectDetail, meetingRecords, speakingResponses, myReviewResponse);
    }

    private String normalizeKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }

        return keyword.trim()
                .replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR + LIKE_ESCAPE_CHAR)
                .replace("%", LIKE_ESCAPE_CHAR + "%")
                .replace("_", LIKE_ESCAPE_CHAR + "_");
    }

    private void validateMember(int memberId) {
        if (!memberRepository.existsById(memberId)) {
            throw new CustomException(ProjectErrorCode.MEMBER_NOT_FOUND);
        }
    }

    private boolean isNotProjectOwner(int projectId, int memberId) {
        return !projectMemberRepository.existsByProjectIdAndMemberIdAndRole(projectId, memberId, ProjectRole.OWNER);
    }

    private Project findProject(int projectId) {
        return projectRepository.findById(projectId)
                .orElseThrow(() ->
                        new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
    }

    private void checkingValidate(int projectId, int memberId) {
        if (isNotExistProject(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }

        if (isNotProjectMember(projectId, memberId)) {
            throw new CustomException(ProjectMemberErrorCode.IS_NOT_PROJECT_MEMBER);
        }
    }

    private boolean isNotExistProject(int projectId) {
        return !projectRepository.existsById(projectId);
    }

    private boolean isNotProjectMember(int projectId, int memberId) {
        return !projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId);
    }

    private ProjectDetailResponse getProjectDetail(int projectId) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
        return ProjectDetailResponse.of(project);
    }

    private List<MeetingReview> getRecentOneMeetingReviews(int projectId, int memberId) {
        return meetingReviewRepository.getRecentReview(projectId, memberId)
                .map(MeetingReview::getRoomName)
                .map(meetingReviewRepository::findAllByRoomName)
                .orElseGet(List::of);
    }

    private MeetingReview findMyReviewOf(List<MeetingReview> recentOneMeetingReviews, int memberId) {
        return recentOneMeetingReviews.stream()
                .filter(mr -> mr.getMemberId() == memberId)
                .findFirst()
                .get();
    }

    private List<MeetingRecordResponse> getRecentFiveMeetingRecord(int projectId) {
        return meetingRecordRepository.findRecentFiveByProjectId(projectId).stream()
                .map(MeetingRecordResponse::of)
                .toList();
    }

    private boolean isRecentReviewNotExist(List<MeetingReview> recentMeetingReviews) {
        return recentMeetingReviews.isEmpty();
    }

    private List<PersonalSpeakingResponse> calculatePersonalSpeakPercentBy(List<MeetingReview> meetingReviews) {
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

    private double toPercent(int speakingSeconds, int totalSpeakTime) {
        if (speakingSeconds == 0 || totalSpeakTime == 0) return 0.0;
        return Math.round(speakingSeconds * 1000.0 / totalSpeakTime) / 10.0;
    }
}
