package com.ssafy.projectree.domain.meeting.record.dto.response;

import java.util.List;

public record MeetingRecordPageResponse(
        List<MeetingRecordListItemResponse> records,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
