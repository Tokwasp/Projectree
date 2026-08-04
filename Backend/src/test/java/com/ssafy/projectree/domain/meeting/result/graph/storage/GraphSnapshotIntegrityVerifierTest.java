package com.ssafy.projectree.domain.meeting.result.graph.storage;

import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GraphSnapshotIntegrityVerifierTest {

    private final GraphSnapshotIntegrityVerifier verifier = new GraphSnapshotIntegrityVerifier();

    @Test
    void verifiesExactMetadataAndRawByteSha256() throws Exception {
        byte[] body = "{\"graph\":1}\n".getBytes(StandardCharsets.UTF_8);
        GraphSnapshotReference reference = reference(body);

        assertThatCode(() -> verifier.verify(reference,
                new DownloadedGraphSnapshot(body, body.length, "application/json")))
                .doesNotThrowAnyException();
        assertThatThrownBy(() -> verifier.verify(reference,
                new DownloadedGraphSnapshot(body, body.length, "application/json;charset=UTF-8")))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        assertThatThrownBy(() -> verifier.verify(reference,
                new DownloadedGraphSnapshot(body, body.length, null)))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        assertThatThrownBy(() -> verifier.verify(reference,
                new DownloadedGraphSnapshot(body, body.length, " ")))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
        assertThatThrownBy(() -> verifier.verify(reference,
                new DownloadedGraphSnapshot("{\"graph\":1}".getBytes(StandardCharsets.UTF_8), body.length,
                        "application/json")))
                .isInstanceOf(GraphSnapshotIntegrityException.class);
    }

    private GraphSnapshotReference reference(byte[] body) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(body);
        StringBuilder hexadecimal = new StringBuilder();
        for (byte value : hash) {
            hexadecimal.append(String.format("%02x", value));
        }
        return new GraphSnapshotReference("graph-bucket", "graph-snapshots/file.json", "application/json",
                body.length, hexadecimal.toString());
    }
}
