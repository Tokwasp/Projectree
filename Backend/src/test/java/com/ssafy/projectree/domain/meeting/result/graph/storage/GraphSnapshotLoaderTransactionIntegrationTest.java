package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.projection.GraphProjectionReplacer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.annotation.Transactional;
import software.amazon.awssdk.services.s3.S3Client;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@SpringBootTest(properties = {
        "app.meeting-analysis.graph-snapshot.s3.enabled=true",
        "app.meeting-analysis.graph-snapshot.s3.expected-bucket=graph-bucket",
        "app.meeting-analysis.graph-snapshot.s3.allowed-object-key-prefix=graph-snapshots/",
        "app.meeting-analysis.graph-snapshot.s3.region=ap-northeast-2"
})
class GraphSnapshotLoaderTransactionIntegrationTest {

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;
    @MockitoBean
    private NaverOAuthClient naverOAuthClient;
    @MockitoBean(name = "graphSnapshotS3Client")
    private S3Client s3Client;
    @Autowired
    private GraphSnapshotLoader loader;
    @Autowired
    private GraphProjectionReplacer projectionReplacer;
    @Autowired
    private ObjectMapper objectMapper;
    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void enabledConfigurationCreatesTheS3ClientAndLoaderBeansWithoutAwsCalls() {
        org.assertj.core.api.Assertions.assertThat(applicationContext.getBeansOfType(S3Client.class)).hasSize(1);
        org.assertj.core.api.Assertions.assertThat(applicationContext.getBeansOfType(GraphSnapshotLoader.class)).hasSize(1);
    }

    @Test
    @Transactional
    void rejectsInvocationInsideExistingDatabaseTransaction() {
        assertThatThrownBy(() -> loader.load(event(), payload()))
                .isInstanceOf(IllegalTransactionStateException.class);
    }

    @Test
    void rejectsProjectionReplacementWithoutApplierTransaction() {
        assertThatThrownBy(() -> projectionReplacer.replace(1, null, Instant.now()))
                .isInstanceOf(IllegalTransactionStateException.class);
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(), 1, 1, UUID.randomUUID().toString(), objectMapper.createObjectNode()
        );
    }

    private ProjectGraphChangedPayload payload() {
        return new ProjectGraphChangedPayload(GraphResultSourceType.MEETING_ANALYSIS, 1,
                new GraphSnapshotReference("graph-bucket", "graph-snapshots/file.json", "application/json", 1,
                        "a".repeat(64)));
    }
}
