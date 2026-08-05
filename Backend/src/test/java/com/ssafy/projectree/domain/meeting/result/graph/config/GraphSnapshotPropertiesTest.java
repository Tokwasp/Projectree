package com.ssafy.projectree.domain.meeting.result.graph.config;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GraphSnapshotPropertiesTest {

    @Test
    void disabledS3AllowsEmptyBucketWhileKeepingDefaultPrefix() {
        GraphSnapshotProperties properties = new GraphSnapshotProperties(1024, null);

        assertThat(properties.s3().enabled()).isFalse();
        assertThat(properties.s3().expectedBucket()).isEmpty();
        assertThat(properties.s3().allowedObjectKeyPrefix()).isEqualTo("graph-snapshots/");
    }

    @Test
    void enabledS3RequiresBucketAndRegion() {
        assertThatThrownBy(() -> new GraphSnapshotProperties.S3(true, "", "graph-snapshots/", "ap-northeast-2", ""))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new GraphSnapshotProperties.S3(true, "bucket", "graph-snapshots/", "", ""))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
