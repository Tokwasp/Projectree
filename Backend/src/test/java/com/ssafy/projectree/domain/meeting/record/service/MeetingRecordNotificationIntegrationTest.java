package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordCallbackRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordCallbackResponse;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.repository.NotificationRepository;
import com.ssafy.projectree.domain.notification.service.NotificationPublisher;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@ActiveProfiles("test")
@SpringBootTest
class MeetingRecordNotificationIntegrationTest {

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @MockitoBean
    private RedisMessageListenerContainer redisMessageListenerContainer;

    @MockitoBean
    private NotificationPublisher notificationPublisher;

    @Autowired
    private MeetingRecordCallbackService callbackService;

    @Autowired
    private NotificationRepository notificationRepository;

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MemberRepository memberRepository;

    @AfterEach
    void cleanUp() {
        notificationRepository.deleteAll();
        meetingRecordRepository.deleteAll();
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("최초 Callback 커밋 후 요청자에게 알림을 한 번 저장·발행하고 재시도에는 반복하지 않는다.")
    @Test
    void createsNotificationAfterFirstCallbackOnly() {
        Fixture fixture = fixture();
        MeetingRecordCallbackRequest request = request(fixture.commandId());

        MeetingRecordCallbackResponse first = callbackService.receive(
                fixture.meetingId(),
                request
        );

        assertThat(first.duplicated()).isFalse();
        assertThat(meetingRecordRepository.count()).isEqualTo(1);
        assertThat(notificationRepository.findAll())
                .hasSize(1)
                .extracting(Notification::getType, Notification::getReceiverId)
                .containsExactly(tuple(
                        NotificationType.MEETING_RECORD_CREATED,
                        fixture.memberId()
                ));
        verify(notificationPublisher, times(1))
                .publish(any(NotificationMessage.class));

        MeetingRecordCallbackResponse retry = callbackService.receive(
                fixture.meetingId(),
                request
        );

        assertThat(retry.duplicated()).isTrue();
        assertThat(meetingRecordRepository.count()).isEqualTo(1);
        assertThat(notificationRepository.count()).isEqualTo(1);
        verify(notificationPublisher, times(1))
                .publish(any(NotificationMessage.class));
    }

    private Fixture fixture() {
        String suffix = UUID.randomUUID().toString();
        Member member = memberRepository.saveAndFlush(
                Member.builder()
                        .email("receiver-" + suffix + "@example.com")
                        .name("receiver")
                        .build()
        );
        Project project = Project.builder()
                .title("project")
                .content("content")
                .build();
        ProjectMember creator = ProjectMember.createMember(
                member.getId(),
                ProjectRole.OWNER
        );
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);

        Meeting meeting = Meeting.create(
                project,
                creator,
                UUID.randomUUID().toString()
        );
        meeting.confirmAnalysisOptions(true, false);
        meeting = meetingRepository.saveAndFlush(meeting);

        UUID commandId = UUID.randomUUID();
        outboxRepository.saveAndFlush(MeetingAnalysisCommandOutbox.pending(
                commandId,
                meeting,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{}",
                member.getId(),
                LocalDateTime.now()
        ));
        return new Fixture(meeting.getId(), member.getId(), commandId);
    }

    private MeetingRecordCallbackRequest request(UUID commandId) {
        return new MeetingRecordCallbackRequest(
                1,
                commandId,
                "회의록 제목",
                List.of("요약"),
                List.of("결정"),
                List.of("다음 할 일"),
                List.of("이슈")
        );
    }

    private record Fixture(int meetingId, int memberId, UUID commandId) {
    }
}
