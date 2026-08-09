package com.ssafy.projectree.domain.meeting.scheduler;

import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisReader;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationOutcome;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "app.meeting-sync",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class MeetingRoomSyncScheduler {

    private final MeetingRoomRedisReader redisReader;
    private final MeetingSynchronizationService synchronizationService;

    @Scheduled(fixedDelayString = "${app.meeting-sync.fixed-delay-ms:5000}")
    public void synchronizeMeetings() {
        long startedAt = System.nanoTime();
        List<MeetingRoomRedisEntry> entries;
        try {
            entries = redisReader.findAll();
        } catch (RuntimeException exception) {
            log.error("[MeetingSync] REDIS_READ_FAILED. Current cycle is aborted.", exception);
            return;
        }

        Map<MeetingSynchronizationOutcome, Integer> counts =
                new EnumMap<>(MeetingSynchronizationOutcome.class);
        int failures = 0;

        for (MeetingRoomRedisEntry entry : entries) {
            try {
                MeetingSynchronizationOutcome outcome = synchronizationService.synchronize(entry);
                counts.merge(outcome, 1, Integer::sum);
            } catch (RuntimeException exception) {
                failures++;
                log.error(
                        "[MeetingSync] MEETING_INSERT_FAILED. key={}, projectId={}, roomName={}",
                        entry == null ? null : entry.sourceKey(),
                        entry == null ? null : entry.projectId(),
                        entry == null ? null : entry.roomName(),
                        exception
                );
            }
        }

        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt);
        int created = counts.getOrDefault(MeetingSynchronizationOutcome.CREATED, 0);
        int invalid = counts.getOrDefault(MeetingSynchronizationOutcome.INVALID_ENTRY, 0);
        int projectNotFound = counts.getOrDefault(MeetingSynchronizationOutcome.PROJECT_NOT_FOUND, 0);
        int uniqueCollisions = counts.getOrDefault(MeetingSynchronizationOutcome.UNIQUE_COLLISION, 0);
        int existing = counts.getOrDefault(MeetingSynchronizationOutcome.ALREADY_EXISTS, 0);
        int creatorRegistered = counts.getOrDefault(
                MeetingSynchronizationOutcome.CREATOR_REGISTERED, 0
        );
        int creatorNotFound = counts.getOrDefault(
                MeetingSynchronizationOutcome.CREATOR_PROJECT_MEMBER_NOT_FOUND, 0
        );
        int creatorConflicts = counts.getOrDefault(
                MeetingSynchronizationOutcome.CREATOR_CONFLICT, 0
        );

        if (created == 0
                && invalid == 0
                && projectNotFound == 0
                && uniqueCollisions == 0
                && creatorRegistered == 0
                && creatorNotFound == 0
                && creatorConflicts == 0
                && failures == 0) {
            log.debug(
                    "[MeetingSync] Cycle completed. validEntries={}, existing={}, elapsedMs={}",
                    entries.size(),
                    existing,
                    elapsedMs
            );
            return;
        }

        log.info(
                "[MeetingSync] Cycle completed. validEntries={}, created={}, existing={}, "
                        + "creatorRegistered={}, creatorNotFound={}, creatorConflicts={}, invalid={}, "
                        + "projectNotFound={}, uniqueCollisions={}, failures={}, elapsedMs={}",
                entries.size(),
                created,
                existing,
                creatorRegistered,
                creatorNotFound,
                creatorConflicts,
                invalid,
                projectNotFound,
                uniqueCollisions,
                failures,
                elapsedMs
        );
    }
}
