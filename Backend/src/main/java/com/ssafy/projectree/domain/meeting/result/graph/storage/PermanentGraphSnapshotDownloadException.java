package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;

public class PermanentGraphSnapshotDownloadException extends AnalysisResultContractException {

    public PermanentGraphSnapshotDownloadException(String message, Throwable cause) {
        super(message, cause);
    }

    public PermanentGraphSnapshotDownloadException(String message) {
        super(message);
    }
}
