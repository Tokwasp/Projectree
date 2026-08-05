package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultRetryableException;

public class RetryableGraphSnapshotDownloadException extends AnalysisResultRetryableException {

    public RetryableGraphSnapshotDownloadException(String message, Throwable cause) {
        super(message, cause);
    }
}
