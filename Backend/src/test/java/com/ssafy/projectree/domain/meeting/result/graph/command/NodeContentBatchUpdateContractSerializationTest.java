package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentBatchUpdateRequestedCommand;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class NodeContentBatchUpdateContractSerializationTest extends IntegrationTestSupport {

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void serializesNodeContentBatchUpdateV2Contract() throws Exception {
        UUID commandId = UUID.fromString(
                "e4f3e557-e52d-40ef-90ef-420175659413"
        );
        NodeContentBatchUpdateRequestedCommand command =
                new NodeContentBatchUpdateRequestedCommand(
                        2,
                        commandId,
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        Instant.parse("2026-08-06T06:30:00Z"),
                        4,
                        new NodeContentBatchUpdateRequestedCommand.Payload(
                                List.of(
                                        new NodeContentBatchUpdateRequestedCommand.NodeUpdate(
                                                "0afdda91-2576-54d3-bb87-8e9263b1d17c",
                                                3,
                                                "수정 제목 A"
                                        )
                                ),
                                15
                        )
                );

        var json = objectMapper.readTree(objectMapper.writeValueAsString(command));
        assertThat(json.path("commandSchemaVersion").asInt()).isEqualTo(2);
        assertThat(json.path("commandType").asText())
                .isEqualTo("NODE_CONTENT_UPDATE_REQUESTED");
        assertThat(json.path("projectId").asInt()).isEqualTo(4);
        assertThat(json.path("payload").path("requestedByMemberId").asInt())
                .isEqualTo(15);
        assertThat(json.path("payload").path("nodes").size()).isEqualTo(1);

        var node = json.path("payload").path("nodes").get(0);
        assertThat(node.path("nodeId").asText())
                .isEqualTo("0afdda91-2576-54d3-bb87-8e9263b1d17c");
        assertThat(node.path("expectedNodeVersion").asLong()).isEqualTo(3);
        assertThat(node.path("title").asText()).isEqualTo("수정 제목 A");
    }

    @Test
    void distinguishesNodeSpecificAndCommandLevelRejectionReasons() {
        assertThat(List.of(
                NodeContentUpdateRejectionReason.NODE_NOT_FOUND,
                NodeContentUpdateRejectionReason.NODE_NOT_EDITABLE,
                NodeContentUpdateRejectionReason.MERGED_SOURCE_NOT_EDITABLE,
                NodeContentUpdateRejectionReason.NODE_VERSION_CONFLICT,
                NodeContentUpdateRejectionReason.INVALID_CURRENT_REVISION
        )).allMatch(NodeContentUpdateRejectionReason::requiresFailedNodeId);

        assertThat(List.of(
                NodeContentUpdateRejectionReason.NO_CHANGE,
                NodeContentUpdateRejectionReason.GRAPH_SNAPSHOT_TOO_LARGE
        )).noneMatch(NodeContentUpdateRejectionReason::requiresFailedNodeId);
    }
}
