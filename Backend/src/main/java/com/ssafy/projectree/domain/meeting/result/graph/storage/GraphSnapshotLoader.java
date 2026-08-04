package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotParser;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotValidator;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
@ConditionalOnBean(GraphSnapshotDownloader.class)
public class GraphSnapshotLoader {

    private final GraphSnapshotProperties properties;
    private final GraphSnapshotDownloader downloader;
    private final GraphSnapshotIntegrityVerifier integrityVerifier;
    private final ProjectGraphSnapshotParser parser;
    private final ProjectGraphSnapshotValidator validator;

    @Transactional(propagation = Propagation.NEVER)
    public ProjectGraphSnapshot load(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload
    ) {
        GraphSnapshotReference snapshotRef = requireSnapshotReference(payload);
        validateAllowlist(snapshotRef);
        DownloadedGraphSnapshot downloaded = downloader.download(snapshotRef);
        integrityVerifier.verify(snapshotRef, downloaded);
        return validator.validate(event, payload, parser.parse(downloaded.bytes()));
    }

    private GraphSnapshotReference requireSnapshotReference(ProjectGraphChangedPayload payload) {
        if (payload == null || payload.snapshotRef() == null) {
            throw new AnalysisResultContractException("Graph snapshot reference must not be null");
        }
        return payload.snapshotRef();
    }

    private void validateAllowlist(GraphSnapshotReference snapshotRef) {
        GraphSnapshotProperties.S3 s3 = properties.s3();
        if (!s3.expectedBucket().equals(snapshotRef.bucket())) {
            throw new AnalysisResultContractException("Graph snapshot bucket is not allowed");
        }
        if (!snapshotRef.objectKey().startsWith(s3.allowedObjectKeyPrefix())) {
            throw new AnalysisResultContractException("Graph snapshot object key is not allowed");
        }
    }
}
