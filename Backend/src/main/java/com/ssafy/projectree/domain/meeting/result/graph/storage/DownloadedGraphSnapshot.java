package com.ssafy.projectree.domain.meeting.result.graph.storage;

public record DownloadedGraphSnapshot(
        byte[] bytes,
        long contentLength,
        String contentType
) {
}
