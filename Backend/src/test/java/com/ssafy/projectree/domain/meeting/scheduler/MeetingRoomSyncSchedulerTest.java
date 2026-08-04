package com.ssafy.projectree.domain.meeting.scheduler;

import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisReader;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationOutcome;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingRoomSyncSchedulerTest {

    private static final String FIRST_ROOM = "550e8400-e29b-41d4-a716-446655440000";
    private static final String SECOND_ROOM = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";

    @Mock
    private MeetingRoomRedisReader redisReader;

    @Mock
    private MeetingSynchronizationService synchronizationService;

    private MeetingRoomSyncScheduler scheduler;

    @BeforeEach
    void setUp() {
        scheduler = new MeetingRoomSyncScheduler(redisReader, synchronizationService);
    }

    @DisplayName("SCAN 결과의 모든 entry를 순서대로 동기화한다.")
    @Test
    void synchronizesEveryEntry() {
        MeetingRoomRedisEntry first = entry(1, FIRST_ROOM);
        MeetingRoomRedisEntry second = entry(2, SECOND_ROOM);
        when(redisReader.findAll()).thenReturn(List.of(first, second));
        when(synchronizationService.synchronize(first))
                .thenReturn(MeetingSynchronizationOutcome.CREATED);
        when(synchronizationService.synchronize(second))
                .thenReturn(MeetingSynchronizationOutcome.ALREADY_EXISTS);

        scheduler.synchronizeMeetings();

        InOrder order = inOrder(synchronizationService);
        order.verify(synchronizationService).synchronize(first);
        order.verify(synchronizationService).synchronize(second);
    }

    @DisplayName("한 entry 저장이 실패해도 다음 entry를 계속 처리한다.")
    @Test
    void continuesAfterEntryFailure() {
        MeetingRoomRedisEntry first = entry(1, FIRST_ROOM);
        MeetingRoomRedisEntry second = entry(2, SECOND_ROOM);
        when(redisReader.findAll()).thenReturn(List.of(first, second));
        when(synchronizationService.synchronize(first)).thenThrow(new RuntimeException("db failure"));
        when(synchronizationService.synchronize(second))
                .thenReturn(MeetingSynchronizationOutcome.CREATED);

        scheduler.synchronizeMeetings();

        verify(synchronizationService).synchronize(second);
    }

    @DisplayName("Redis 조회가 실패하면 현재 주기를 중단한다.")
    @Test
    void abortsCurrentCycleWhenRedisReadFails() {
        when(redisReader.findAll()).thenThrow(new RuntimeException("redis unavailable"));

        scheduler.synchronizeMeetings();

        verify(synchronizationService, never())
                .synchronize(org.mockito.ArgumentMatchers.any());
    }

    private MeetingRoomRedisEntry entry(int projectId, String roomName) {
        return new MeetingRoomRedisEntry(
                "meeting:project:" + projectId,
                projectId,
                722,
                roomName
        );
    }
}
