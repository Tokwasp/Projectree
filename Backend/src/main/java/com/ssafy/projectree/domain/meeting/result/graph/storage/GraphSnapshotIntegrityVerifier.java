package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import org.springframework.stereotype.Component;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

@Component
public class GraphSnapshotIntegrityVerifier {

    public void verify(GraphSnapshotReference snapshotRef, DownloadedGraphSnapshot downloaded) {
        if (snapshotRef == null || downloaded == null || downloaded.bytes() == null) {
            throw new GraphSnapshotIntegrityException("Graph snapshot integrity input is invalid");
        }
        long actualLength = downloaded.bytes().length;
        if (downloaded.contentLength() != actualLength || snapshotRef.sizeBytes() != actualLength) {
            throw new GraphSnapshotIntegrityException("Graph snapshot content length does not match");
        }
        if (downloaded.contentType() == null || downloaded.contentType().isBlank()
                || !snapshotRef.contentType().equals(downloaded.contentType())
                || !"application/json".equals(downloaded.contentType())) {
            throw new GraphSnapshotIntegrityException("Graph snapshot content type does not match");
        }
        if (!snapshotRef.sha256().equals(toSha256(downloaded.bytes()))) {
            throw new GraphSnapshotIntegrityException("Graph snapshot SHA-256 does not match");
        }
    }

    private String toSha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder hexadecimal = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                hexadecimal.append(String.format("%02x", value));
            }
            return hexadecimal.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
