package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;

public class GraphSnapshotIntegrityException extends AnalysisResultContractException {

    public GraphSnapshotIntegrityException(String message) {
        super(message);
    }
}
