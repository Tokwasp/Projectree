package com.ssafy.projectree.domain.meeting.result.graph.config;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotDownloader;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import software.amazon.awssdk.services.s3.S3Client;

import static org.assertj.core.api.Assertions.assertThat;

class GraphSnapshotS3DisabledTest extends IntegrationTestSupport {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void disabledS3CreatesNoClientDownloaderOrLoader() {
        assertThat(applicationContext.getBeansOfType(S3Client.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(GraphSnapshotDownloader.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(GraphSnapshotLoader.class)).isEmpty();
    }
}
