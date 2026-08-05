package com.ssafy.projectree.domain.meeting.dto.response;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;

import java.util.UUID;

public record MeetingAnalysisRequestResponse(
        int meetingId,
        int projectId,
        String roomName,
        boolean generateSummary,
        AnalysisTaskStatus summaryStatus,
        boolean generateNodes,
        AnalysisTaskStatus nodeStatus,
        UUID commandId
) {

    public static MeetingAnalysisRequestResponse of(Meeting meeting, UUID commandId) {
        return new MeetingAnalysisRequestResponse(
                meeting.getId(),
                meeting.getProject().getId(),
                meeting.getRoomName(),
                meeting.isGenerateSummary(),
                meeting.getSummaryStatus(),
                meeting.isGenerateNodes(),
                meeting.getNodeStatus(),
                commandId
        );
    }
}
