package com.ssafy.projectree.domain.meeting.result.graph.config;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotDownloader;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestPropertySource;
import software.amazon.awssdk.services.s3.S3Client;

import static org.assertj.core.api.Assertions.assertThat;

@TestPropertySource(properties = {
        "app.meeting-analysis.graph-snapshot.s3.enabled=false",
        "MEETING_ANALYSIS_GRAPH_SNAPSHOT_S3_ENABLED=false"
})
class GraphSnapshotS3DisabledTest extends IntegrationTestSupport {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void disabledS3CreatesNoClientDownloaderOrLoader() {
        assertThat(applicationContext.getBeansOfType(S3Client.class))
                .doesNotContainKey("graphSnapshotS3Client");
        assertThat(applicationContext.getBeansOfType(GraphSnapshotDownloader.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(GraphSnapshotLoader.class)).isEmpty();
    }
}
