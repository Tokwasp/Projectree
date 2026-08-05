package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotParser;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotValidator;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

import java.lang.reflect.Method;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class GraphSnapshotLoaderTest {

    private final GraphSnapshotDownloader downloader = mock(GraphSnapshotDownloader.class);
    private final GraphSnapshotIntegrityVerifier integrityVerifier = mock(GraphSnapshotIntegrityVerifier.class);
    private final ProjectGraphSnapshotParser parser = mock(ProjectGraphSnapshotParser.class);
    private final ProjectGraphSnapshotValidator validator = mock(ProjectGraphSnapshotValidator.class);
    private final GraphSnapshotLoader loader = new GraphSnapshotLoader(
            new GraphSnapshotProperties(10, new GraphSnapshotProperties.S3(
                    true, "graph-bucket", "graph-snapshots/", "ap-northeast-2", "")),
            downloader, integrityVerifier, parser, validator
    );

    @Test
    void loadsInTheRequiredOrderAndReturnsNormalizedSnapshot() {
        Fixture fixture = fixture("graph-snapshots/file.json");
        DownloadedGraphSnapshot downloaded = new DownloadedGraphSnapshot(new byte[]{1}, 1, "application/json");
        ProjectGraphSnapshot parsed = mock(ProjectGraphSnapshot.class);
        ProjectGraphSnapshot normalized = mock(ProjectGraphSnapshot.class);
        given(downloader.download(fixture.payload().snapshotRef())).willReturn(downloaded);
        given(parser.parse(downloaded.bytes())).willReturn(parsed);
        given(validator.validate(fixture.event(), fixture.payload(), parsed)).willReturn(normalized);

        assertThat(loader.load(fixture.event(), fixture.payload())).isSameAs(normalized);

        InOrder order = inOrder(downloader, integrityVerifier, parser, validator);
        order.verify(downloader).download(fixture.payload().snapshotRef());
        order.verify(integrityVerifier)
                .verify(fixture.payload().snapshotRef(), downloaded);
        order.verify(parser).parse(downloaded.bytes());
        order.verify(validator)
                .validate(fixture.event(), fixture.payload(), parsed);
    }

    @Test
    void rejectsDisallowedBucketOrPrefixBeforeCallingS3() {
        Fixture invalidPrefix = fixture("elsewhere/file.json");
        assertThatThrownBy(() -> loader.load(invalidPrefix.event(), invalidPrefix.payload()))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> loader.load(fixture("graph-snapshots/file.json").event(), new ProjectGraphChangedPayload(
                GraphResultSourceType.MEETING_ANALYSIS, 1,
                new GraphSnapshotReference("other-bucket", "graph-snapshots/file.json", "application/json", 1, "a".repeat(64)))))
                .isInstanceOf(AnalysisResultContractException.class);
        verify(downloader, never()).download(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void loadIsExplicitlyForbiddenInsideDatabaseTransaction() throws Exception {
        Method method = GraphSnapshotLoader.class.getMethod("load", AnalysisResultEventEnvelope.class,
                ProjectGraphChangedPayload.class);
        Transactional transactional = method.getAnnotation(Transactional.class);

        assertThat(transactional.propagation()).isEqualTo(Propagation.NEVER);
    }

    @Test
    void doesNotParseWhenIntegrityFailsOrValidateWhenParsingFails() {
        Fixture fixture = fixture("graph-snapshots/file.json");
        DownloadedGraphSnapshot downloaded = new DownloadedGraphSnapshot(new byte[]{1}, 1, "application/json");
        given(downloader.download(fixture.payload().snapshotRef())).willReturn(downloaded);
        org.mockito.Mockito.doThrow(new GraphSnapshotIntegrityException("invalid"))
                .when(integrityVerifier).verify(fixture.payload().snapshotRef(), downloaded);

        assertThatThrownBy(() -> loader.load(fixture.event(), fixture.payload()))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        verify(parser, never()).parse(org.mockito.ArgumentMatchers.any());
        verify(validator, never()).validate(org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void doesNotValidateWhenStrictParsingFails() {
        Fixture fixture = fixture("graph-snapshots/file.json");
        DownloadedGraphSnapshot downloaded = new DownloadedGraphSnapshot(new byte[]{1}, 1, "application/json");
        given(downloader.download(fixture.payload().snapshotRef())).willReturn(downloaded);
        given(parser.parse(downloaded.bytes())).willThrow(new AnalysisResultContractException("invalid JSON"));

        assertThatThrownBy(() -> loader.load(fixture.event(), fixture.payload()))
                .isInstanceOf(AnalysisResultContractException.class);
        verify(validator, never()).validate(org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    private Fixture fixture(String objectKey) {
        String commandId = UUID.randomUUID().toString();
        AnalysisResultEventEnvelope event = new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(), 1, 1, commandId, JsonMapper.builder().build().createObjectNode()
        );
        return new Fixture(event, new ProjectGraphChangedPayload(GraphResultSourceType.MEETING_ANALYSIS, 1,
                new GraphSnapshotReference("graph-bucket", objectKey, "application/json", 1, "a".repeat(64))));
    }

    private record Fixture(AnalysisResultEventEnvelope event, ProjectGraphChangedPayload payload) {
    }
}
