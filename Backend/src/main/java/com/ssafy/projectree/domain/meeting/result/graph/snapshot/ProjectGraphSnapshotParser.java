package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.MapperFeature;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.cfg.EnumFeature;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

@Component
@RequiredArgsConstructor
public class ProjectGraphSnapshotParser {

    private final ObjectMapper objectMapper;

    public ProjectGraphSnapshot parse(byte[] snapshotBytes) {
        if (snapshotBytes == null || snapshotBytes.length == 0) {
            throw new AnalysisResultContractException("Graph snapshot bytes must not be empty");
        }
        String json = decodeUtf8(snapshotBytes);
        try {
            ProjectGraphSnapshot snapshot = objectMapper.rebuild()
                    .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
                    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
                    .enable(EnumFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
                    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                    .build()
                    .readValue(json, ProjectGraphSnapshot.class);
            validateMergeRecords(snapshot);
            return snapshot;
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException("Graph snapshot JSON is invalid", exception);
        }
    }

    private String decodeUtf8(byte[] snapshotBytes) {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(snapshotBytes))
                    .toString();
        } catch (CharacterCodingException exception) {
            throw new AnalysisResultContractException("Graph snapshot must be valid UTF-8", exception);
        }
    }

    private void validateMergeRecords(ProjectGraphSnapshot snapshot) {
        if (snapshot.mergeRecords() == null || snapshot.mergeRecords().stream()
                .anyMatch(node -> node == null || node.isNull())) {
            throw new AnalysisResultContractException("Graph snapshot mergeRecords must not contain null");
        }
    }
}
