package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

@Component
@RequiredArgsConstructor
@ConditionalOnBean(name = "graphSnapshotS3Client")
public class GraphSnapshotDownloader {

    private final @Qualifier("graphSnapshotS3Client") S3Client s3Client;
    private final GraphSnapshotProperties properties;

    public DownloadedGraphSnapshot download(GraphSnapshotReference snapshotRef) {
        validateExpectedSize(snapshotRef);
        ResponseInputStream<GetObjectResponse> response = null;
        boolean fullyConsumed = false;
        try {
            response = s3Client.getObject(GetObjectRequest.builder()
                    .bucket(snapshotRef.bucket())
                    .key(snapshotRef.objectKey())
                    .build());
            GetObjectResponse metadata = response.response();
            long contentLength = requireContentLength(metadata);
            if (contentLength != snapshotRef.sizeBytes()) {
                throw new GraphSnapshotIntegrityException("Graph snapshot content length does not match event size");
            }
            byte[] bytes = readBounded(response, snapshotRef.sizeBytes());
            fullyConsumed = true;
            if (bytes.length != snapshotRef.sizeBytes() || bytes.length != contentLength) {
                throw new GraphSnapshotIntegrityException("Graph snapshot body length does not match metadata");
            }
            return new DownloadedGraphSnapshot(bytes, contentLength, metadata.contentType());
        } catch (GraphSnapshotIntegrityException exception) {
            abortIfIncomplete(response, fullyConsumed);
            throw exception;
        } catch (S3Exception exception) {
            abortIfIncomplete(response, fullyConsumed);
            throw classifyS3Exception(exception);
        } catch (SdkClientException | IOException exception) {
            abortIfIncomplete(response, fullyConsumed);
            throw new RetryableGraphSnapshotDownloadException("Graph snapshot download failed", exception);
        } catch (RuntimeException exception) {
            abortIfIncomplete(response, fullyConsumed);
            throw exception;
        } finally {
            if (fullyConsumed) {
                close(response);
            }
        }
    }

    private void validateExpectedSize(GraphSnapshotReference snapshotRef) {
        if (snapshotRef == null || snapshotRef.sizeBytes() <= 0 || snapshotRef.sizeBytes() > properties.maxSizeBytes()) {
            throw new GraphSnapshotIntegrityException("Graph snapshot event size is outside allowed range");
        }
    }

    private long requireContentLength(GetObjectResponse metadata) {
        Long contentLength = metadata.contentLength();
        if (contentLength == null || contentLength < 0 || contentLength > properties.maxSizeBytes()) {
            throw new GraphSnapshotIntegrityException("Graph snapshot content length is outside allowed range");
        }
        return contentLength;
    }

    private byte[] readBounded(InputStream input, long expectedSizeBytes) throws IOException {
        try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            long total = 0;
            long limit = expectedSizeBytes + 1;
            while (total < limit) {
                int maximumRead = (int) Math.min(buffer.length, limit - total);
                int read = input.read(buffer, 0, maximumRead);
                if (read == -1) {
                    return output.toByteArray();
                }
                if (read == 0) {
                    throw new IOException("Graph snapshot stream returned zero bytes");
                }
                total += read;
                if (total > expectedSizeBytes) {
                    throw new GraphSnapshotIntegrityException("Graph snapshot body exceeds expected size");
                }
                output.write(buffer, 0, read);
            }
            throw new GraphSnapshotIntegrityException("Graph snapshot body exceeds expected size");
        }
    }

    private RuntimeException classifyS3Exception(S3Exception exception) {
        int statusCode = exception.statusCode();
        if (statusCode == 408 || statusCode == 429 || statusCode >= 500) {
            return new RetryableGraphSnapshotDownloadException("Graph snapshot S3 request is retryable", exception);
        }
        return new PermanentGraphSnapshotDownloadException("Graph snapshot S3 request failed permanently", exception);
    }

    private void abortIfIncomplete(ResponseInputStream<GetObjectResponse> response, boolean fullyConsumed) {
        if (response != null && !fullyConsumed) {
            try {
                response.abort();
            } catch (RuntimeException ignored) {
                // Preserve the original download failure.
            }
        }
    }

    private void close(ResponseInputStream<GetObjectResponse> response) {
        if (response != null) {
            try {
                response.close();
            } catch (IOException exception) {
                abortIfIncomplete(response, false);
            }
        }
    }
}
