package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.ProjectreeApplication;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("test")
@SpringBootTest(
        classes = {
                ProjectreeApplication.class,
                CommandOutboxClaimServiceIntegrationTest.FixedClockConfig.class
        },
        properties = "app.meeting-analysis.publisher.batch-size=1"
)
class CommandOutboxClaimServiceIntegrationTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 4, 10, 0);

    @Autowired
    private CommandOutboxClaimService claimService;
    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Autowired
    private MeetingRepository meetingRepository;
    @Autowired
    private ProjectRepository projectRepository;

    @AfterEach
    void cleanUp() {
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
    }

    @Test
    void claimsDuePendingButNotFuturePendingAndHonorsBatchOrder() {
        MeetingAnalysisCommandOutbox first = savePending(NOW);
        savePending(NOW);
        savePending(NOW.plusMinutes(1));

        List<ClaimedCommandOutbox> claimed = claimService.claimAvailable();

        assertThat(claimed).hasSize(1);
        assertThat(claimed.get(0).outboxId()).isEqualTo(first.getId());
        MeetingAnalysisCommandOutbox stored = outboxRepository
                .findById(first.getId())
                .orElseThrow();
        assertThat(stored.getAttemptCount()).isEqualTo(1);
        assertThat(stored.getClaimToken()).isEqualTo(claimed.get(0).claimToken());
        assertThat(stored.getLeaseUntil()).isEqualTo(NOW.plusSeconds(60));
    }

    @Test
    void validLeaseIsNotClaimedButExpiredLeaseIsReclaimedWithoutIncrement() {
        MeetingAnalysisCommandOutbox active = savePending(NOW);
        String activeToken = active.claim(NOW, NOW.plusSeconds(10), 3);
        outboxRepository.saveAndFlush(active);
        assertThat(claimService.claimAvailable()).isEmpty();

        MeetingAnalysisCommandOutbox expired = outboxRepository.findById(active.getId()).orElseThrow();
        org.springframework.test.util.ReflectionTestUtils.setField(
                expired,
                "leaseUntil",
                NOW.minusSeconds(1)
        );
        outboxRepository.saveAndFlush(expired);

        List<ClaimedCommandOutbox> reclaimed = claimService.claimAvailable();

        assertThat(reclaimed).hasSize(1);
        assertThat(reclaimed.get(0).attemptCount()).isEqualTo(1);
        assertThat(reclaimed.get(0).claimToken()).isNotEqualTo(activeToken);
    }

    @Test
    void concurrentInstancesDoNotClaimSameRow() throws Exception {
        MeetingAnalysisCommandOutbox outbox = savePending(NOW);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<List<ClaimedCommandOutbox>> first =
                    executor.submit(() -> claimAfterSignal(ready, start));
            Future<List<ClaimedCommandOutbox>> second =
                    executor.submit(() -> claimAfterSignal(ready, start));
            ready.await();
            start.countDown();

            List<ClaimedCommandOutbox> all = new java.util.ArrayList<>();
            all.addAll(first.get());
            all.addAll(second.get());

            assertThat(all).hasSize(1);
            assertThat(all.get(0).outboxId()).isEqualTo(outbox.getId());
        }
    }

    private List<ClaimedCommandOutbox> claimAfterSignal(
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        return claimService.claimAvailable();
    }

    private MeetingAnalysisCommandOutbox savePending(LocalDateTime nextAttemptAt) {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, creator, UUID.randomUUID().toString())
        );
        return outboxRepository.saveAndFlush(MeetingAnalysisCommandOutbox.pending(
                UUID.randomUUID(),
                meeting,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{\"stored\":true}",
                17,
                nextAttemptAt
        ));
    }

    @TestConfiguration
    static class FixedClockConfig {
        @Bean
        @Primary
        Clock fixedMeetingAnalysisClock() {
            return Clock.fixed(
                    Instant.parse("2026-08-04T01:00:00Z"),
                    ZoneId.of("Asia/Seoul")
            );
        }
    }
}
