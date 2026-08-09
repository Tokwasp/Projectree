package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisReader;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationErrorCode;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.inbox.entity.MeetingAnalysisResultInbox;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import com.ssafy.projectree.domain.meetingreview.exception.MeetingReviewErrorCode;
import com.ssafy.projectree.domain.meetingreview.repository.MeetingReviewRepository;
import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.controller.dto.response.home.ProjectHomeResponse;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectMemberErrorCode;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;

class ProjectServiceTest extends IntegrationTestSupport {

    @Autowired
    private ProjectService projectService;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MeetingReviewRepository meetingReviewRepository;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectGraphSyncRepository projectGraphSyncRepository;

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private ProjectInvitationRepository projectInvitationRepository;

    @Autowired
    private InvitationMailRepository invitationMailRepository;

    @Autowired
    private ProjectNodeProjectionRepository projectNodeProjectionRepository;

    @Autowired
    private NodeEvidenceProjectionRepository nodeEvidenceProjectionRepository;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository commandOutboxRepository;

    @Autowired
    private MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;

    @Autowired
    private MeetingAnalysisResultInboxRepository resultInboxRepository;

    @Autowired
    private NodeDeleteCommandRepository nodeDeleteCommandRepository;

    @Autowired
    private NodeDeleteCommandItemRepository nodeDeleteCommandItemRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @MockitoBean
    private MeetingRoomRedisReader meetingRoomRedisReader;

    @DisplayName("프로젝트를 생성하면 생성된 프로젝트의 id를 반환한다.")
    @Test
    void createProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());

        // then
        assertThat(projectId).isPositive();
        assertThat(projectGraphSyncRepository.findById(projectId))
                .get()
                .satisfies(sync -> {
                    assertThat(sync.getCurrentGraphVersion()).isZero();
                    assertThat(sync.hasActiveCommand()).isFalse();
                });
    }

    @DisplayName("프로젝트를 생성하면 제목/설명/이미지 URL이 그대로 저장된다.")
    @Test
    void createProject_persistsFields() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", "https://cdn.example.com/thumb.png");

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found)
                .extracting("title", "content", "photoUrl")
                .containsExactly(
                        "포트폴리오 사이트",
                        "React로 만든 개인 포트폴리오입니다.",
                        "https://cdn.example.com/thumb.png"
                );
    }

    @DisplayName("프로젝트를 생성하면 생성한 회원이 OWNER로 참여 멤버에 등록된다.")
    @Test
    void createProject_registersCreatorAsOwner() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectMembers()).hasSize(1)
                .first()
                .extracting(ProjectMember::getMemberId, ProjectMember::getRole)
                .containsExactly(member.getId(), ProjectRole.OWNER);
    }

    @DisplayName("생성된 ProjectMember는 프로젝트와 양방향으로 연결된다.")
    @Test
    void createProject_linksProjectMemberToProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectMembers().get(0).getProject().getId())
                .isEqualTo(projectId);
    }

    @DisplayName("photoUrl이 없어도 프로젝트를 생성할 수 있다.")
    @Test
    void createProject_withoutPhotoUrl() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getPhotoUrl()).isNull();
    }

    @DisplayName("존재하지 않는 회원 id로 프로젝트를 생성하면 MEMBER_NOT_FOUND 예외가 발생한다.")
    @Test
    void createProject_memberNotFound() {
        // given
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when // then
        assertThatThrownBy(() -> projectService.createProject(request, 999))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.MEMBER_NOT_FOUND);
    }

    @DisplayName("존재하지 않는 회원 id로 프로젝트 생성에 실패하면 프로젝트가 저장되지 않는다.")
    @Test
    void createProject_memberNotFound_savesNothing() {
        // given
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        assertThatThrownBy(() -> projectService.createProject(request, 999))
                .isInstanceOf(CustomException.class);

        // then
        assertThat(projectRepository.count()).isZero();
    }

    @DisplayName("OWNER가 프로젝트 이미지를 수정하면 photoUrl이 변경된다.")
    @Test
    void updateImage() {
        // given
        Member owner = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        projectService.updateImage(projectId, owner.getId(), "https://cdn.example.com/new.png");
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getPhotoUrl()).isEqualTo("https://cdn.example.com/new.png");
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 이미지를 수정하려 하면 IS_NOT_PROJECT_OWNER 예외가 발생한다.")
    @Test
    void updateImage_notOwner() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when // then
        assertThatThrownBy(() -> projectService.updateImage(projectId, member.getId(), "https://cdn.example.com/new.png"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
    }

    @DisplayName("존재하지 않는 프로젝트의 이미지를 수정하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void updateImage_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.updateImage(999, member.getId(), "https://cdn.example.com/new.png"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("OWNER가 프로젝트 제목을 수정하면 title이 변경된다.")
    @Test
    void updateTitle() {
        // given
        Member owner = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        projectService.updateTitle(projectId, owner.getId(), "수정된 제목");
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getTitle()).isEqualTo("수정된 제목");
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 제목을 수정하려 하면 IS_NOT_PROJECT_OWNER 예외가 발생한다.")
    @Test
    void updateTitle_notOwner() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when // then
        assertThatThrownBy(() -> projectService.updateTitle(projectId, member.getId(), "수정된 제목"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
    }

    @DisplayName("존재하지 않는 프로젝트의 제목을 수정하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void updateTitle_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.updateTitle(999, member.getId(), "수정된 제목"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("OWNER가 프로젝트 내용을 수정하면 content가 변경된다.")
    @Test
    void updateContent() {
        // given
        Member owner = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        projectService.updateContent(projectId, owner.getId(), "수정된 내용");
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getContent()).isEqualTo("수정된 내용");
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 내용을 수정하려 하면 IS_NOT_PROJECT_OWNER 예외가 발생한다.")
    @Test
    void updateContent_notOwner() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when // then
        assertThatThrownBy(() -> projectService.updateContent(projectId, member.getId(), "수정된 내용"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectMemberErrorCode.IS_NOT_PROJECT_OWNER);
    }

    @DisplayName("존재하지 않는 프로젝트의 내용을 수정하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void updateContent_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.updateContent(999, member.getId(), "수정된 내용"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("OWNER는 자신의 프로젝트를 삭제할 수 있다.")
    @Test
    void deleteProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(member);

        // when
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isEmpty();
        assertThat(projectGraphSyncRepository.findById(projectId)).isEmpty();
    }

    @Test
    void deleteProjectWithActiveGraphOperationIsRejectedWithoutDeletingAggregate() {
        Member owner = memberRepository.save(createMember("owner-guard@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        ProjectGraphSync sync = projectGraphSyncRepository.findById(projectId)
                .orElseThrow();
        sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                Instant.now()
        );
        projectGraphSyncRepository.saveAndFlush(sync);

        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(projectGraphSyncRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1);
    }

    @Test
    void deleteProjectWithMissingGraphSyncFailsWithoutDeletingAggregate() {
        Member owner = memberRepository.save(createMember("owner-missing-sync@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        projectGraphSyncRepository.deleteById(projectId);
        projectGraphSyncRepository.flush();

        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND);
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1);
    }

    @DisplayName("프로젝트를 삭제하면 참여 멤버도 함께 삭제된다.")
    @Test
    void deleteProject_cascadesChildren() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // when
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // then
        assertThat(countProjectMembers()).isZero();
    }

    @DisplayName("종료된 Meeting과 회의록, 리뷰가 있어도 프로젝트 aggregate를 삭제한다.")
    @Test
    void deleteProject_removesHistoricalMeetingAggregate() {
        Member owner = memberRepository.save(createMember("owner-history@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        Project project = projectRepository.findById(projectId).orElseThrow();
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, project.getProjectMembers().getFirst(), UUID.randomUUID().toString())
        );
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting,
                UUID.randomUUID(),
                "회의록",
                null,
                null,
                null,
                null
        ));
        meetingReviewRepository.saveAndFlush(MeetingReview.of(
                meeting.getRoomName(),
                projectId,
                owner.getId()
        ));
        Member invitee = memberRepository.save(createMember("invitee-history@gmail.com", "초대대상"));
        ProjectInvitation invitation = projectInvitationRepository.saveAndFlush(ProjectInvitation.builder()
                .project(project)
                .inviterMemberId(owner.getId())
                .inviteeMemberId(invitee.getId())
                .tokenHash(UUID.randomUUID().toString())
                .lastInvitedAt(LocalDateTime.now())
                .build());
        invitationMailRepository.saveAndFlush(InvitationMail.queue(
                invitation.getId(),
                invitee.getEmail(),
                "https://projectree.site/invitations/token"
        ));
        String nodeId = UUID.randomUUID().toString();
        projectNodeProjectionRepository.saveAndFlush(ProjectNodeProjection.from(
                projectId,
                new ProjectGraphSnapshotNode(
                        nodeId,
                        meeting.getId(),
                        null,
                        null,
                        GraphNodeType.DECISION,
                        GraphNodeCategory.BACKEND,
                        GraphNodeState.ACTIVE,
                        "노드",
                        "내용",
                        GraphLinkSource.LLM_GENERATED,
                        1,
                        Instant.now(),
                        Instant.now()
                ),
                Instant.now()
        ));
        nodeEvidenceProjectionRepository.saveAndFlush(NodeEvidenceProjection.from(
                new ProjectGraphSnapshotEvidence(
                        UUID.randomUUID().toString(),
                        nodeId,
                        meeting.getId(),
                        "근거",
                        null,
                        null,
                        null,
                        0
                ),
                Instant.now()
        ));
        commandOutboxRepository.saveAndFlush(MeetingAnalysisCommandOutbox.pending(
                UUID.randomUUID(),
                meeting,
                com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{\"command\":\"historical\"}",
                owner.getId(),
                LocalDateTime.now()
        ));
        notificationOutboxRepository.saveAndFlush(MeetingAnalysisNotificationOutbox.pending(
                UUID.randomUUID().toString(),
                meeting.getId(),
                projectId,
                owner.getId(),
                NotificationAudience.USER,
                "{\"notification\":\"historical\"}"
        ));

        projectService.deleteProject(projectId, owner.getId());
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isEmpty();
        assertThat(meetingRepository.findById(meeting.getId())).isEmpty();
        assertThat(meetingRecordRepository.findByMeetingId(meeting.getId())).isEmpty();
        assertThat(count("select count(*) from meeting_review where project_id = " + projectId)).isZero();
        assertThat(count("select count(*) from project_invitation where project_id = " + projectId)).isZero();
        assertThat(count("select count(*) from project_invitation_mail where invitation_id = " + invitation.getId())).isZero();
        assertThat(projectNodeProjectionRepository.countByProjectId(projectId)).isZero();
        assertThat(nodeEvidenceProjectionRepository.countByNodeId(nodeId)).isZero();
        assertThat(projectGraphSyncRepository.findById(projectId)).isEmpty();
        assertThat(commandOutboxRepository.countByMeetingId(meeting.getId())).isZero();
        assertThat(notificationOutboxRepository.count()).isZero();
    }

    @Test
    void deleteProject_removesNodeDeleteCommandHistory() {
        Member owner = memberRepository.save(createMember("owner-node-delete-history@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        UUID commandId = UUID.randomUUID();
        LocalDateTime requestedAt = LocalDateTime.now();
        NodeDeleteCommand command = nodeDeleteCommandRepository.saveAndFlush(
                NodeDeleteCommand.pending(
                        commandId,
                        projectId,
                        0L,
                        owner.getId(),
                        1,
                        0,
                        requestedAt
                )
        );
        NodeDeleteCommandItem item = nodeDeleteCommandItemRepository.saveAndFlush(
                NodeDeleteCommandItem.requested(
                        command,
                        UUID.randomUUID().toString(),
                        1L,
                        requestedAt
                )
        );
        flushAndClear();

        projectService.deleteProject(projectId, owner.getId());
        flushAndClear();

        assertThat(nodeDeleteCommandItemRepository.findById(item.getId())).isEmpty();
        assertThat(nodeDeleteCommandRepository.findById(command.getId())).isEmpty();
    }

    @DisplayName("PROCESSING summary 분석이 있으면 프로젝트 삭제를 막고 데이터를 유지한다.")
    @Test
    void deleteProject_rejectsProcessingSummaryAnalysis() {
        Member owner = memberRepository.save(createMember("owner-processing-summary@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        Project project = projectRepository.findById(projectId).orElseThrow();
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, project.getProjectMembers().getFirst(), UUID.randomUUID().toString())
        );
        meeting.confirmAnalysisOptions(true, false);
        meetingRepository.flush();

        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_ANALYSIS_IN_PROGRESS);

        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(meetingRepository.findById(meeting.getId()))
                .isPresent()
                .get()
                .extracting(Meeting::getSummaryStatus)
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("PROCESSING node 분석이 있으면 프로젝트 삭제를 막는다.")
    @Test
    void deleteProject_rejectsProcessingNodeAnalysis() {
        Member owner = memberRepository.save(createMember("owner-processing-node@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        Project project = projectRepository.findById(projectId).orElseThrow();
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, project.getProjectMembers().getFirst(), UUID.randomUUID().toString())
        );
        meeting.confirmAnalysisOptions(false, true);
        meetingRepository.flush();

        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_ANALYSIS_IN_PROGRESS);

        assertThat(projectRepository.findById(projectId)).isPresent();
    }

    @DisplayName("Redis에 활성 회의방이 있으면 프로젝트 삭제를 막고 데이터를 유지한다.")
    @Test
    void deleteProject_rejectsActiveMeetingRoom() {
        Member owner = memberRepository.save(createMember("owner-active-room@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        org.mockito.BDDMockito.given(meetingRoomRedisReader.existsByProjectId(projectId)).willReturn(true);

        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_ACTIVE_MEETING);

        assertThat(projectRepository.findById(projectId)).isPresent();
    }

    @DisplayName("PUBLISHED 상태의 meeting 없는 Node Content Update는 Result 처리 전까지 프로젝트 삭제를 막는다.")
    @Test
    void deleteProject_rejectsPublishedNodeContentUpdateWithoutTerminalResult() {
        Member owner = memberRepository.save(createMember("owner-node-update-in-flight@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        MeetingAnalysisCommandOutbox outbox = saveNodeContentUpdateOutbox(projectId, owner.getId());
        LocalDateTime now = LocalDateTime.now();
        String claimToken = outbox.claim(now, now.plusMinutes(1), 3);
        outbox.markPublished(claimToken, now);
        commandOutboxRepository.saveAndFlush(outbox);

        assertThat(outbox.getMeeting()).isNull();
        assertThat(outbox.getTargetProjectId()).isEqualTo(projectId);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);
        assertThatThrownBy(() -> projectService.deleteProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);

        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(commandOutboxRepository.findById(outbox.getId())).isPresent();
    }

    @DisplayName("Node Content Update의 PROJECT_GRAPH_CHANGED가 Inbox에 terminal 처리되면 프로젝트를 삭제할 수 있다.")
    @Test
    void deleteProject_allowsTerminalNodeContentUpdate() {
        Member owner = memberRepository.save(createMember("owner-node-update-terminal@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        MeetingAnalysisCommandOutbox outbox = saveNodeContentUpdateOutbox(projectId, owner.getId());
        resultInboxRepository.saveAndFlush(MeetingAnalysisResultInbox.processed(
                new AnalysisResultEventEnvelope(
                        1,
                        UUID.randomUUID().toString(),
                        AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                        Instant.now(),
                        projectId,
                        null,
                        outbox.getCommandId(),
                        null
                ),
                Instant.now()
        ));

        projectService.deleteProject(projectId, owner.getId());
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isEmpty();
    }

    @DisplayName("Node Content Update Outbox가 영구 FAILED이면 프로젝트 삭제를 막지 않는다.")
    @Test
    void deleteProject_allowsPermanentlyFailedNodeContentUpdate() {
        Member owner = memberRepository.save(createMember("owner-node-update-failed@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);
        MeetingAnalysisCommandOutbox outbox = saveNodeContentUpdateOutbox(projectId, owner.getId());
        LocalDateTime now = LocalDateTime.now();
        String claimToken = outbox.claim(now, now.plusMinutes(1), 1);
        outbox.rescheduleOrFail(claimToken, now, 1, 1, 1, "publish failed");
        commandOutboxRepository.saveAndFlush(outbox);

        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.FAILED);
        projectService.deleteProject(projectId, owner.getId());
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isEmpty();
    }

    @DisplayName("다른 프로젝트의 in-flight Node Content Update는 현재 프로젝트 삭제를 막지 않는다.")
    @Test
    void deleteProject_ignoresOtherProjectsInFlightNodeContentUpdate() {
        Member owner = memberRepository.save(createMember("owner-node-update-other@gmail.com", "김오너"));
        int targetProjectId = createProjectOwnedBy(owner);
        int otherProjectId = projectService.createProject(
                createRequest("다른 프로젝트", null),
                owner.getId()
        );
        saveNodeContentUpdateOutbox(otherProjectId, owner.getId());

        projectService.deleteProject(targetProjectId, owner.getId());
        flushAndClear();

        assertThat(projectRepository.findById(targetProjectId)).isEmpty();
        assertThat(projectRepository.findById(otherProjectId)).isPresent();
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 삭제하려 하면 PROJECT_DELETE_FORBIDDEN 예외가 발생한다.")
    @Test
    void deleteProject_withMemberRole() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member participant = memberRepository.save(createMember("member@gmail.com", "이싸피"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, participant);

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, participant.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
    }

    @DisplayName("프로젝트에 참여하지 않은 회원이 삭제하려 하면 PROJECT_DELETE_FORBIDDEN 예외가 발생한다.")
    @Test
    void deleteProject_notParticipating() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, stranger.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
    }

    @DisplayName("삭제 권한이 없어 실패하면 프로젝트와 자식 행이 그대로 남는다.")
    @Test
    void deleteProject_forbidden_deletesNothing() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        assertThatThrownBy(() -> projectService.deleteProject(projectId, stranger.getId()))
                .isInstanceOf(CustomException.class);
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1L);
    }

    @DisplayName("존재하지 않는 프로젝트를 삭제하려 하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void deleteProject_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(999, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("프로젝트 존재 검증이 권한 검증보다 먼저 수행된다.")
    @Test
    void deleteProject_validatesProjectBeforePermission() {
        // given
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(999, stranger.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("같은 프로젝트를 두 번 삭제하면 두 번째는 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void deleteProject_twice() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(member);
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("한 프로젝트를 삭제해도 다른 프로젝트는 남는다.")
    @Test
    void deleteProject_doesNotAffectOtherProjects() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int target = createProjectOwnedBy(member);
        int other = projectService.createProject(
                createRequest("스터디 관리 앱", null), member.getId());
        flushAndClear();

        // when
        projectService.deleteProject(target, member.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(target)).isEmpty();
        assertThat(projectRepository.findById(other)).isPresent();
    }

    @DisplayName("프로젝트에 참여하지 않은 회원이 탈퇴하려 하면 PROJECT_PARTICIPANT_NOT_FOUND 예외가 발생하고 아무것도 지워지지 않는다.")
    @Test
    void leaveProject_notParticipating() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        assertThatThrownBy(() -> projectService.leaveProject(projectId, stranger.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1L);
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 탈퇴하면 자신만 프로젝트에서 빠지고 프로젝트는 그대로 남는다.")
    @Test
    void leaveProject_withMemberRole_removesOnlySelf() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when
        projectService.leaveProject(projectId, member.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1L);
    }

    @DisplayName("OWNER가 탈퇴하면 프로젝트와 참여 멤버 전원이 함께 삭제된다.")
    @Test
    void leaveProject_byOwner_deletesProjectAndMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when
        projectService.leaveProject(projectId, owner.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isEmpty();
        assertThat(projectGraphSyncRepository.findById(projectId)).isEmpty();
        assertThat(countProjectMembers()).isZero();
    }

    @Test
    void ownerLeaveWithActiveGraphOperationIsRejectedWithoutRemovingMembers() {
        Member owner = memberRepository.save(createMember("leave-owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("leave-member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);
        ProjectGraphSync sync = projectGraphSyncRepository.findById(projectId)
                .orElseThrow();
        sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.now()
        );
        projectGraphSyncRepository.saveAndFlush(sync);

        assertThatThrownBy(() -> projectService.leaveProject(projectId, owner.getId()))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);
        flushAndClear();

        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(projectGraphSyncRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(2);
    }

    @DisplayName("프로젝트 참여자가 팀원 목록을 조회하면 참여자 전원이 회원 정보와 함께 반환된다.")
    @Test
    void getProjectMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, member.getId());

        // then
        assertThat(result)
                .extracting("memberId", "name", "email", "role")
                .containsExactly(
                        tuple(owner.getId(), "김오너", "owner@gmail.com", ProjectRole.OWNER),
                        tuple(member.getId(), "이멤버", "member@gmail.com", ProjectRole.MEMBER)
                );
    }

    @DisplayName("OWNER 도 자기 프로젝트의 팀원 목록을 조회할 수 있다.")
    @Test
    void getProjectMembers_byOwner() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, owner.getId());

        // then
        assertThat(result).hasSize(1);
        assertThat(result.getFirst().getRole()).isEqualTo(ProjectRole.OWNER);
    }

    @DisplayName("참여하지 않은 회원이 팀원 목록을 조회하면 예외가 발생한다.")
    @Test
    void getProjectMembers_notParticipant() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));
        int projectId = createProjectOwnedBy(owner);

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(projectId, outsider.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND.getMessage());
    }

    @DisplayName("존재하지 않는 프로젝트의 팀원 목록을 조회하면 예외가 발생한다.")
    @Test
    void getProjectMembers_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(999_999, member.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_NOT_FOUND.getMessage());
    }

    @DisplayName("프로젝트 존재 검증이 참여자 검증보다 먼저 수행된다.")
    @Test
    void getProjectMembers_validatesProjectBeforeParticipant() {
        // given
        // 프로젝트도 없고 참여자도 아닌 상황에서 어떤 예외가 나오는지로 검증 순서를 확인한다
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(999_999, outsider.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_NOT_FOUND.getMessage());
    }

    @DisplayName("다른 프로젝트의 팀원은 목록에 포함되지 않는다.")
    @Test
    void getProjectMembers_excludesOtherProjectMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));
        int target = createProjectOwnedBy(owner);
        int other = projectService.createProject(
                createRequest("스터디 관리 앱", null), outsider.getId());
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(target, owner.getId());

        // then
        assertThat(other).isNotEqualTo(target);
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    @DisplayName("탈퇴한 회원은 팀원 목록에서 빠진다.")
    @Test
    void getProjectMembers_afterLeave() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        projectService.leaveProject(projectId, member.getId());
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, owner.getId());

        // then
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    @DisplayName("프로젝트에 참여하지 않은 회원이 홈을 조회하면 IS_NOT_PROJECT_MEMBER 예외가 발생한다.")
    @Test
    void getProjectHome_notProjectMember() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));
        int projectId = createProjectOwnedBy(owner);

        // when // then
        assertThatThrownBy(() ->
                projectService.getProjectHome(projectId, outsider.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectMemberErrorCode.IS_NOT_PROJECT_MEMBER);
    }

    @DisplayName("회의 리뷰가 없는 프로젝트의 홈을 조회하면 빈 홈이 반환된다.")
    @Test
    void getProjectHome_noMeetingReview() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));

        String projectTitle = "포트폴리오 사이트";
        String content = "React로 만든 개인 포트폴리오입니다.";
        int projectId = createProjectOwnedBy(owner, projectTitle, content, 1);

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getProjectDetail())
                .extracting("projectTitle", "projectContent", "participantCount")
                .containsExactly("포트폴리오 사이트", "React로 만든 개인 포트폴리오입니다.", 1);

        assertThat(response.getMeetingRecordList()).isEmpty();
        assertThat(response.getPersonalSpeakingList()).isEmpty();
        assertThat(response.getMyReview()).isNull();
    }

    @DisplayName("프로젝트에 2명이 참여한 상태로 홈을 조회하면 참가자 수가 2로 반환된다.")
    @Test
    void getProjectHome_participantCount() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getProjectDetail().getParticipantCount()).isEqualTo(2);
    }

    @DisplayName("프로젝트 홈을 조회하면 로그인한 회원의 가장 최근 회의 리뷰가 myReview로 반환된다.")
    @Test
    void getProjectHome_myReview() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        String roomName = "room-" + projectId;
        saveMeetingReview(roomName, projectId, owner.getId(), 40,
                "속도가 적절합니다.", "발언량이 충분합니다.", "회의가 원활했습니다.");
        saveMeetingReview(roomName, projectId, member.getId(), 60,
                "다른 사람 피드백", "다른 사람 피드백", "다른 사람 피드백");
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getMyReview())
                .extracting("speedFeedback", "personalFeedback", "overallFeedback")
                .containsExactly("속도가 적절합니다.", "발언량이 충분합니다.", "회의가 원활했습니다.");
    }

    @DisplayName("프로젝트 홈을 조회하면 같은 회의에 참석한 전원의 발화 비율이 계산되어 반환된다.")
    @Test
    void getProjectHome_personalSpeakingList() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member1 = memberRepository.save(createMember("member1@gmail.com", "이멤버"));
        Member member2 = memberRepository.save(createMember("member2@gmail.com", "박멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member1);
        joinAsMember(projectId, member2);

        String roomName = "room-" + projectId;
        saveMeetingReview(roomName, projectId, owner.getId(), 50, "", "", "");
        saveMeetingReview(roomName, projectId, member1.getId(), 30, "", "", "");
        saveMeetingReview(roomName, projectId, member2.getId(), 20, "", "", "");
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getPersonalSpeakingList()).hasSize(3)
                .extracting("name", "speakPercent")
                .containsExactlyInAnyOrder(
                        tuple("김오너", 50.0),
                        tuple("이멤버", 30.0),
                        tuple("박멤버", 20.0)
                );
    }

    @DisplayName("프로젝트 홈을 조회하면 내 리뷰와 참석자 발화 비율이 함께 반환된다.")
    @Test
    void getProjectHome() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        String roomName = "room-" + projectId;
        saveMeetingReview(roomName, projectId, owner.getId(), 70,
                "속도가 빠릅니다.", "발언이 많습니다.", "적극적인 회의였습니다.");
        saveMeetingReview(roomName, projectId, member.getId(), 30, "", "", "");
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getMeetingRecordList()).isEmpty();
        assertThat(response.getMyReview())
                .extracting("speedFeedback", "personalFeedback", "overallFeedback")
                .containsExactly("속도가 빠릅니다.", "발언이 많습니다.", "적극적인 회의였습니다.");
        assertThat(response.getPersonalSpeakingList()).hasSize(2)
                .extracting("name", "speakPercent")
                .containsExactlyInAnyOrder(
                        tuple("김오너", 70.0),
                        tuple("이멤버", 30.0)
                );
    }

    @DisplayName("프로젝트 홈을 조회하면 로그인한 회원의 회의 리뷰가 없는 경우 프로젝트 내용과 회의록이 조회된다.")
    @Test
    void getProjectHome_meetingRecordWithoutMyReview() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));

        String projectTitle = "포트폴리오 사이트";
        String content = "React로 만든 개인 포트폴리오입니다.";
        int projectId = createProjectOwnedBy(owner, projectTitle, content, 1);

        int firstMeetingId = saveMeetingRecord(projectId, "1회차 회의록");
        int secondMeetingId = saveMeetingRecord(projectId, "2회차 회의록");
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getProjectDetail())
                .extracting("projectTitle", "projectContent", "participantCount")
                .containsExactly("포트폴리오 사이트", "React로 만든 개인 포트폴리오입니다.", 1);

        assertThat(response.getMeetingRecordList()).hasSize(2)
                .extracting("meetingId", "name")
                .containsExactly(
                        tuple(secondMeetingId, "2회차 회의록"),
                        tuple(firstMeetingId, "1회차 회의록")
                );

        assertThat(response.getPersonalSpeakingList()).isEmpty();
        assertThat(response.getMyReview()).isNull();
    }

    @DisplayName("프로젝트 홈을 조회하면 회의록이 없는 회의는 회의록 목록에서 제외된다.")
    @Test
    void getProjectHome_excludesMeetingWithoutRecord() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);

        int meetingId = saveMeetingRecord(projectId, "1회차 회의록");
        saveMeetingWithoutRecord(projectId);
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getMeetingRecordList()).hasSize(1)
                .extracting("meetingId", "name")
                .containsExactly(tuple(meetingId, "1회차 회의록"));
    }

    @DisplayName("프로젝트 홈을 조회하면 회의 리뷰가 있는 경우 프로젝트 내용, 회의록, 발화 비율, 내 리뷰가 모두 조회되고 회의록은 최근순으로 정렬된다.")
    @Test
    void getProjectHome_allContents() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));

        String projectTitle = "포트폴리오 사이트";
        String content = "React로 만든 개인 포트폴리오입니다.";
        int projectId = createProjectOwnedBy(owner, projectTitle, content, 1);
        joinAsMember(projectId, member);

        int firstMeetingId = saveMeetingRecord(projectId, "1회차 회의록");
        int secondMeetingId = saveMeetingRecord(projectId, "2회차 회의록");
        int thirdMeetingId = saveMeetingRecord(projectId, "3회차 회의록");

        String roomName = "room-" + projectId;
        saveMeetingReview(roomName, projectId, owner.getId(), 70,
                "속도가 빠릅니다.", "발언이 많습니다.", "적극적인 회의였습니다.");
        saveMeetingReview(roomName, projectId, member.getId(), 30, "", "", "");
        flushAndClear();

        // when
        ProjectHomeResponse response =
                projectService.getProjectHome(projectId, owner.getId());

        // then
        assertThat(response.getProjectDetail())
                .extracting("projectTitle", "projectContent", "participantCount")
                .containsExactly("포트폴리오 사이트", "React로 만든 개인 포트폴리오입니다.", 2);

        assertThat(response.getMeetingRecordList()).hasSize(3)
                .extracting("meetingId", "name")
                .containsExactly(
                        tuple(thirdMeetingId, "3회차 회의록"),
                        tuple(secondMeetingId, "2회차 회의록"),
                        tuple(firstMeetingId, "1회차 회의록")
                );

        assertThat(response.getMyReview())
                .extracting("speedFeedback", "personalFeedback", "overallFeedback")
                .containsExactly("속도가 빠릅니다.", "발언이 많습니다.", "적극적인 회의였습니다.");

        assertThat(response.getPersonalSpeakingList()).hasSize(2)
                .extracting("name", "speakPercent")
                .containsExactlyInAnyOrder(
                        tuple("김오너", 70.0),
                        tuple("이멤버", 30.0)
                );
    }

    private int createProjectOwnedBy(Member owner) {
        return createProjectOwnedBy(owner, "포트폴리오 사이트", "React로 만든 개인 포트폴리오입니다.", 1);
    }

    private int createProjectOwnedBy(Member owner, String title, String content, int participantCount) {
        ProjectCreateRequest request = ProjectCreateRequest.builder()
                .title(title)
                .content(content)
                .build();

        int projectId = projectService.createProject(request, owner.getId());
        flushAndClear();

        for (int i = 1; i < participantCount; i++) {
            Member member = memberRepository.save(
                    createMember("member" + i + "-" + projectId + "@gmail.com", "멤버" + i));
            joinAsMember(projectId, member);
        }

        return projectId;
    }

    private void joinAsMember(int projectId, Member member) {
        Project project = projectRepository.findById(projectId).orElseThrow();
        project.addMember(ProjectMember.createMember(member.getId(), ProjectRole.MEMBER));
        flushAndClear();
    }

    private Long countProjectMembers() {
        return count("select count(*) from project_member");
    }

    private Long countProjectCategories() {
        return count("select count(*) from project_category");
    }

    private Long count(String sql) {
        Number count = (Number) entityManager.createNativeQuery(sql).getSingleResult();
        return count.longValue();
    }

    private void flushAndClear() {
        entityManager.flush();
        entityManager.clear();
    }

    private int saveMeetingRecord(int projectId, String title) {
        Project project = projectRepository.findById(projectId).orElseThrow();
        Meeting meeting = meetingRepository.save(
                Meeting.create(project, project.getProjectMembers().get(0), UUID.randomUUID().toString()));

        meetingRecordRepository.save(
                MeetingRecord.create(meeting, UUID.randomUUID(), title, null, null, null, null));
        return meeting.getId();
    }

    private void saveMeetingWithoutRecord(int projectId) {
        Project project = projectRepository.findById(projectId).orElseThrow();
        meetingRepository.save(
                Meeting.create(project, project.getProjectMembers().get(0), UUID.randomUUID().toString()));
    }

    private MeetingAnalysisCommandOutbox saveNodeContentUpdateOutbox(
            int projectId,
            int requestedByMemberId
    ) {
        return commandOutboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                        UUID.randomUUID(),
                        projectId,
                        UUID.randomUUID().toString(),
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        "{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}",
                        requestedByMemberId,
                        LocalDateTime.now()
                )
        );
    }

    private void saveMeetingReview(String roomName, int projectId, int memberId, int speakingSeconds,
                                   String speedFeedback, String personalFeedback, String overallFeedback) {
        meetingReviewRepository.save(MeetingReview.of(roomName, projectId, memberId, speakingSeconds,
                speedFeedback, personalFeedback, overallFeedback));
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

    private ProjectCreateRequest createRequest(String title, String photoUrl) {
        return createRequest(title, photoUrl, List.of(1));
    }

    private ProjectCreateRequest createRequest(String title, String photoUrl, List<Integer> categoryIds) {
        return ProjectCreateRequest.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .photoUrl(photoUrl)
                .build();
    }
}
