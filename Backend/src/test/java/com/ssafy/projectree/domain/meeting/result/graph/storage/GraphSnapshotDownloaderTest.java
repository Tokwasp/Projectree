package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class GraphSnapshotDownloaderTest {

    private final S3Client s3Client = mock(S3Client.class);
    private final GraphSnapshotDownloader downloader = new GraphSnapshotDownloader(s3Client, properties(10));

    @Test
    void downloadsBoundedBytesWithTheExactEventBucketAndKey() throws Exception {
        ResponseInputStream<GetObjectResponse> response = response("abc".getBytes(), 3L);
        given(s3Client.getObject(any(GetObjectRequest.class))).willReturn(response);

        DownloadedGraphSnapshot downloaded = downloader.download(reference(3));

        ArgumentCaptor<GetObjectRequest> request = ArgumentCaptor.forClass(GetObjectRequest.class);
        verify(s3Client).getObject(request.capture());
        assertThat(request.getValue().bucket()).isEqualTo("graph-bucket");
        assertThat(request.getValue().key()).isEqualTo("graph-snapshots/file.json");
        assertThat(downloaded.bytes()).containsExactly((byte) 'a', (byte) 'b', (byte) 'c');
        verify(response).close();
    }

    @Test
    void rejectsOversizedOrMismatchedMetadataBeforeReadingBody() throws Exception {
        ResponseInputStream<GetObjectResponse> oversized = response("abc".getBytes(), 11L);
        given(s3Client.getObject(any(GetObjectRequest.class))).willReturn(oversized);

        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        verify(oversized).abort();

        reset(s3Client);
        assertThatThrownBy(() -> downloader.download(reference(11)))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        verifyNoInteractions(s3Client);
    }

    @Test
    void rejectsBodyThatExceedsTheBoundOrDoesNotMatchMetadata() throws Exception {
        ResponseInputStream<GetObjectResponse> tooLargeBody = response("abcdefghijk".getBytes(), 3L);
        given(s3Client.getObject(any(GetObjectRequest.class))).willReturn(tooLargeBody);

        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        verify(tooLargeBody).abort();

        ResponseInputStream<GetObjectResponse> shorterBody = response("ab".getBytes(), 3L);
        given(s3Client.getObject(any(GetObjectRequest.class))).willReturn(shorterBody);
        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        verify(shorterBody).close();
    }

    @Test
    void classifiesTransientAndPermanentS3Failures() {
        given(s3Client.getObject(any(GetObjectRequest.class)))
                .willThrow(S3Exception.builder().statusCode(503).build());
        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(RetryableGraphSnapshotDownloadException.class);

        given(s3Client.getObject(any(GetObjectRequest.class)))
                .willThrow(S3Exception.builder().statusCode(403).build());
        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(PermanentGraphSnapshotDownloadException.class);

        given(s3Client.getObject(any(GetObjectRequest.class)))
                .willThrow(S3Exception.builder().statusCode(404).build());
        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(PermanentGraphSnapshotDownloadException.class);

        given(s3Client.getObject(any(GetObjectRequest.class)))
                .willThrow(SdkClientException.builder().message("network").build());
        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(RetryableGraphSnapshotDownloadException.class);
    }

    @Test
    void abortsAnIncompleteStreamWhenReadingFails() throws Exception {
        ResponseInputStream<GetObjectResponse> response = mock(ResponseInputStream.class);
        given(response.response()).willReturn(GetObjectResponse.builder()
                .contentLength(3L)
                .contentType("application/json")
                .build());
        given(s3Client.getObject(any(GetObjectRequest.class))).willReturn(response);
        given(response.read(any(byte[].class), any(Integer.class), any(Integer.class)))
                .willThrow(new IOException("read failed"));

        assertThatThrownBy(() -> downloader.download(reference(3)))
                .isInstanceOf(RetryableGraphSnapshotDownloadException.class);
        verify(response).abort();
    }

    @SuppressWarnings("unchecked")
    private ResponseInputStream<GetObjectResponse> response(byte[] body, long contentLength) throws IOException {
        ResponseInputStream<GetObjectResponse> response = mock(ResponseInputStream.class);
        given(response.response()).willReturn(GetObjectResponse.builder()
                .contentLength(contentLength)
                .contentType("application/json")
                .build());
        AtomicInteger offset = new AtomicInteger();
        doAnswer(invocation -> {
            byte[] buffer = invocation.getArgument(0);
            int destinationOffset = invocation.getArgument(1);
            int maximumRead = invocation.getArgument(2);
            int remaining = body.length - offset.get();
            if (remaining == 0) {
                return -1;
            }
            int count = Math.min(maximumRead, remaining);
            System.arraycopy(body, offset.getAndAdd(count), buffer, destinationOffset, count);
            return count;
        }).when(response).read(any(byte[].class), any(Integer.class), any(Integer.class));
        return response;
    }

    private GraphSnapshotReference reference(long sizeBytes) {
        return new GraphSnapshotReference("graph-bucket", "graph-snapshots/file.json", "application/json",
                sizeBytes, "a".repeat(64));
    }

    private GraphSnapshotProperties properties(long maxSizeBytes) {
        return new GraphSnapshotProperties(maxSizeBytes,
                new GraphSnapshotProperties.S3(true, "graph-bucket", "graph-snapshots/", "ap-northeast-2", ""));
    }
}
