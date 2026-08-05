package com.ssafy.projectree.domain.meeting.result.graph.event;

public record GraphSnapshotReference(
        String bucket,
        String objectKey,
        String contentType,
        long sizeBytes,
        String sha256
) {
}
