package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

public record ProjectGraphSnapshotEvidence(
        String evidenceId,
        String nodeId,
        int meetingId,
        String quoteText,
        String speakerLabel,
        Long startMs,
        Long endMs,
        int evidenceOrder
) {
}
