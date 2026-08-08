package com.ssafy.projectree.domain.meeting.record.dto.response;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record MeetingRecordListItemResponse(
        long meetingRecordId,
        int meetingId,
        String title,
        LocalDate meetingDate,
        LocalDateTime startedAt,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
}
