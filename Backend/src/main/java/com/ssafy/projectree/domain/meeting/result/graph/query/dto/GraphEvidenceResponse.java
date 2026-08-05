package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

public record GraphEvidenceResponse(
        String evidenceId,
        int meetingId,
        String quoteText,
        String speakerLabel,
        Long startMs,
        Long endMs,
        int evidenceOrder
) {
}
