package com.ssafy.projectree.domain.meeting.record.dto.response;

import java.time.LocalDateTime;
import java.util.List;

public record MeetingRecordUpdateResponse(
        long meetingRecordId,
        int projectId,
        int meetingId,
        String title,
        List<String> summary,
        List<String> decisions,
        List<String> nextTodos,
        List<String> issues,
        long version,
        LocalDateTime updatedAt
) {
}
