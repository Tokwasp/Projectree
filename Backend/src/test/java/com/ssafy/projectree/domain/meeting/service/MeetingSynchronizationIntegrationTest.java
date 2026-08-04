package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.scheduler.MeetingRoomSyncScheduler;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("test")
@SpringBootTest
class MeetingSynchronizationIntegrationTest {

    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private MeetingSynchronizationService synchronizationService;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ApplicationContext applicationContext;

    @AfterEach
    void cleanUp() {
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @DisplayName("같은 roomName을 동시에 동기화해도 Meeting은 최종 1건만 생성된다.")
    @Test
    void concurrentSynchronizationCreatesOnlyOneMeeting() throws Exception {
        Project project = projectRepository.saveAndFlush(
                Project.builder().title("project").content("content").build()
        );
        MeetingRoomRedisEntry entry = new MeetingRoomRedisEntry(
                "meeting-room:" + ROOM_NAME,
                project.getId(),
                ROOM_NAME
        );
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<MeetingSynchronizationOutcome> first =
                    executor.submit(() -> synchronizeAfterSignal(entry, ready, start));
            Future<MeetingSynchronizationOutcome> second =
                    executor.submit(() -> synchronizeAfterSignal(entry, ready, start));

            ready.await();
            start.countDown();

            List<MeetingSynchronizationOutcome> outcomes = List.of(first.get(), second.get());
            assertThat(outcomes).contains(MeetingSynchronizationOutcome.CREATED);
            assertThat(outcomes)
                    .anyMatch(outcome -> outcome == MeetingSynchronizationOutcome.ALREADY_EXISTS
                            || outcome == MeetingSynchronizationOutcome.UNIQUE_COLLISION);
        }

        assertThat(meetingRepository.count()).isEqualTo(1);
        assertThat(meetingRepository.findByRoomName(ROOM_NAME)).isPresent();
    }

    @DisplayName("같은 Redis entry를 반복 처리해도 Meeting은 추가 생성되지 않는다.")
    @Test
    void repeatedSynchronizationIsIdempotent() {
        Project project = projectRepository.saveAndFlush(
                Project.builder().title("project").content("content").build()
        );
        MeetingRoomRedisEntry entry = new MeetingRoomRedisEntry(
                "meeting-room:" + ROOM_NAME,
                project.getId(),
                ROOM_NAME
        );

        assertThat(synchronizationService.synchronize(entry))
                .isEqualTo(MeetingSynchronizationOutcome.CREATED);
        assertThat(synchronizationService.synchronize(entry))
                .isEqualTo(MeetingSynchronizationOutcome.ALREADY_EXISTS);
        assertThat(meetingRepository.count()).isEqualTo(1);
    }

    @DisplayName("app.meeting-sync.enabled=false이면 Scheduler Bean을 만들지 않는다.")
    @Test
    void schedulerIsDisabledByTestConfiguration() {
        assertThat(applicationContext.getBeansOfType(MeetingRoomSyncScheduler.class)).isEmpty();
    }

    private MeetingSynchronizationOutcome synchronizeAfterSignal(
            MeetingRoomRedisEntry entry,
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        return synchronizationService.synchronize(entry);
    }
}
