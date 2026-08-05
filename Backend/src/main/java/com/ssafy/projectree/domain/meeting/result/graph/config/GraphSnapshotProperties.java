package com.ssafy.projectree.domain.meeting.result.graph.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.meeting-analysis.graph-snapshot")
public record GraphSnapshotProperties(
        long maxSizeBytes,
        S3 s3
) {

    public GraphSnapshotProperties {
        if (maxSizeBytes <= 0 || maxSizeBytes >= Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Graph snapshot maximum size is invalid");
        }
        s3 = s3 == null ? new S3(false, "", "graph-snapshots/", "", "") : s3;
    }

    public record S3(
            boolean enabled,
            String expectedBucket,
            String allowedObjectKeyPrefix,
            String region,
            String endpointOverride
    ) {

        public S3 {
            expectedBucket = expectedBucket == null ? "" : expectedBucket;
            allowedObjectKeyPrefix = allowedObjectKeyPrefix == null ? "graph-snapshots/" : allowedObjectKeyPrefix;
            region = region == null ? "" : region;
            endpointOverride = endpointOverride == null ? "" : endpointOverride;
            if (allowedObjectKeyPrefix.isBlank()) {
                throw new IllegalArgumentException("Graph snapshot S3 object key prefix must not be blank");
            }
            if (enabled && (expectedBucket.isBlank() || region.isBlank())) {
                throw new IllegalArgumentException("Enabled graph snapshot S3 requires bucket and region");
            }
        }
    }
}
