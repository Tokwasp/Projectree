package com.ssafy.projectree.domain.meeting.result.graph.event;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.regex.Pattern;

@Component
@RequiredArgsConstructor
public class ProjectGraphChangedPayloadValidator {

    private static final Pattern SHA_256 = Pattern.compile("[0-9a-f]{64}");
    private final GraphSnapshotProperties properties;

    public void validate(ProjectGraphChangedPayload payload) {
        if (payload == null || payload.sourceType() != GraphResultSourceType.MEETING_ANALYSIS) {
            throw new AnalysisResultContractException("Graph result sourceType must be MEETING_ANALYSIS");
        }
        if (payload.graphVersion() <= 0) {
            throw new AnalysisResultContractException("graphVersion must be positive");
        }
        GraphSnapshotReference snapshotRef = payload.snapshotRef();
        if (snapshotRef == null) {
            throw new AnalysisResultContractException("snapshotRef must not be null");
        }
        validateBucket(snapshotRef.bucket());
        validateObjectKey(snapshotRef.objectKey());
        if (!"application/json".equals(snapshotRef.contentType())) {
            throw new AnalysisResultContractException("snapshotRef contentType must be application/json");
        }
        if (snapshotRef.sizeBytes() <= 0 || snapshotRef.sizeBytes() > properties.maxSizeBytes()) {
            throw new AnalysisResultContractException("snapshotRef sizeBytes is outside allowed range");
        }
        if (snapshotRef.sha256() == null || !SHA_256.matcher(snapshotRef.sha256()).matches()) {
            throw new AnalysisResultContractException("snapshotRef sha256 must be lowercase SHA-256 hexadecimal");
        }
    }

    private void validateBucket(String bucket) {
        requireLength(bucket, "snapshotRef bucket", 255);
        if (bucket.startsWith("s3://") || bucket.contains("://") || bucket.contains("/") || bucket.contains("\\")) {
            throw new AnalysisResultContractException("snapshotRef bucket must be a bucket name only");
        }
        try {
            URI uri = new URI(bucket);
            if (uri.getScheme() != null || uri.getHost() != null
                    || uri.getRawQuery() != null || uri.getRawFragment() != null) {
                throw new AnalysisResultContractException("snapshotRef bucket must not contain a scheme or host");
            }
        } catch (URISyntaxException exception) {
            throw new AnalysisResultContractException("snapshotRef bucket is invalid", exception);
        }
    }

    private void validateObjectKey(String objectKey) {
        requireLength(objectKey, "snapshotRef objectKey", 1024);
        if (objectKey.startsWith("/") || objectKey.contains("\\") || objectKey.contains("://")) {
            throw new AnalysisResultContractException("snapshotRef objectKey must be a relative S3 key");
        }
        for (String segment : objectKey.split("/", -1)) {
            if ("..".equals(segment)) {
                throw new AnalysisResultContractException("snapshotRef objectKey must not contain .. segments");
            }
        }
        try {
            URI uri = new URI(objectKey);
            if (uri.isAbsolute() || uri.getHost() != null) {
                throw new AnalysisResultContractException("snapshotRef objectKey must not be a URL");
            }
        } catch (URISyntaxException exception) {
            throw new AnalysisResultContractException("snapshotRef objectKey is invalid", exception);
        }
    }

    private void requireLength(String value, String fieldName, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new AnalysisResultContractException(fieldName + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new AnalysisResultContractException(fieldName + " exceeds maximum length");
        }
    }
}
