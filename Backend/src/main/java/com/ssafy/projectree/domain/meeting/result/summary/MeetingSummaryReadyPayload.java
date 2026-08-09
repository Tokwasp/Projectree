package com.ssafy.projectree.domain.meeting.result.summary;

public record MeetingSummaryReadyPayload(
        String meetingSummaryId,
        int summaryVersion,
        MeetingSummaryResultStatus status,
        String apiPath
) {
}
