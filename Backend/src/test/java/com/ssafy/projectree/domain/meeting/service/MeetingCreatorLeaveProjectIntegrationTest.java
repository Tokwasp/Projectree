package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.service.ProjectService;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@SpringBootTest
class MeetingCreatorLeaveProjectIntegrationTest {

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private ProjectService projectService;

    @Autowired
    private MeetingAnalysisRequestService analysisRequestService;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MemberRepository memberRepository;

    @AfterEach
    void cleanUp() {
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("Meeting 생성자인 MEMBER도 프로젝트에서 탈퇴할 수 있고 생성자 기록은 유지된다.")
    @Test
    void meetingCreatorMemberCanLeaveProject() {
        Fixture fixture = fixture();

        projectService.leaveProject(fixture.projectId(), fixture.creatorMemberId());
        projectMemberRepository.flush();

        assertThat(projectMemberRepository.existsByProjectIdAndMemberId(
                fixture.projectId(),
                fixture.creatorMemberId()
        )).isFalse();
        assertThat(meetingRepository.findById(fixture.meetingId()))
                .isPresent()
                .get()
                .extracting(Meeting::getCreatorMemberId)
                .isEqualTo(fixture.creatorMemberId());
    }

    @DisplayName("탈퇴한 Meeting 생성자는 분석 요청 시 접근 거부되고 상태와 Outbox는 변경되지 않는다.")
    @Test
    void departedMeetingCreatorCannotRequestAnalysis() {
        Fixture fixture = fixture();
        projectService.leaveProject(fixture.projectId(), fixture.creatorMemberId());

        assertThatThrownBy(() -> analysisRequestService.requestAnalysis(
                fixture.projectId(),
                fixture.roomName(),
                fixture.creatorMemberId(),
                new MeetingAnalysisRequest(true, true)
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(MeetingErrorCode.MEETING_ACCESS_DENIED);

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isZero();
    }

    private Fixture fixture() {
        String suffix = UUID.randomUUID().toString();
        Member owner = memberRepository.saveAndFlush(
                Member.builder()
                        .email("owner-" + suffix + "@example.com")
                        .name("owner")
                        .build()
        );
        Member creator = memberRepository.saveAndFlush(
                Member.builder()
                        .email("creator-" + suffix + "@example.com")
                        .name("creator")
                        .build()
        );

        Project project = Project.builder()
                .title("project")
                .content("content")
                .build();
        project.addMember(ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        ProjectMember creatorProjectMember =
                ProjectMember.createMember(creator.getId(), ProjectRole.MEMBER);
        project.addMember(creatorProjectMember);
        project = projectRepository.saveAndFlush(project);

        String roomName = UUID.randomUUID().toString();
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, creatorProjectMember, roomName)
        );
        return new Fixture(project.getId(), creator.getId(), meeting.getId(), roomName);
    }

    private record Fixture(
            int projectId,
            int creatorMemberId,
            int meetingId,
            String roomName
    ) {
    }
}
