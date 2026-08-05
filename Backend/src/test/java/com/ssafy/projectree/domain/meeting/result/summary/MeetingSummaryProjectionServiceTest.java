package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class MeetingSummaryProjectionServiceTest {

    @Mock
    private MeetingSummaryProjectionRepository repository;

    @Test
    void newProjectionUsesInjectedClockForSyncedAt() {
        Instant syncedAt = Instant.parse("2026-08-04T12:40:00Z");
        MeetingSummaryProjectionService service = new MeetingSummaryProjectionService(
                repository, Clock.fixed(syncedAt, ZoneOffset.UTC)
        );
        AnalysisResultEventEnvelope event = new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.MEETING_SUMMARY_READY,
                Instant.parse("2026-08-04T12:31:00Z"), 1, 2, UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
        MeetingSummaryReadyPayload payload = new MeetingSummaryReadyPayload(
                UUID.randomUUID().toString(), 1, MeetingSummaryResultStatus.READY,
                "/api/v1/meetings/2/summary?summaryVersion=1"
        );
        given(repository.findByMeetingId(2)).willReturn(Optional.empty());

        service.apply(event, payload);

        ArgumentCaptor<MeetingSummaryProjection> captor = ArgumentCaptor.forClass(
                MeetingSummaryProjection.class
        );
        verify(repository).saveAndFlush(captor.capture());
        assertThat(captor.getValue().getSyncedAt()).isEqualTo(syncedAt);
        assertThat(captor.getValue().getOccurredAt()).isEqualTo(event.occurredAt());
    }
}
