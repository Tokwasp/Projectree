package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import jakarta.persistence.Column;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class NodeDeleteSchemaTest {

    private static final Path DDL =
            Path.of("docs/migrations/20260807_create_node_delete_command.sql");

    @Test
    void entitiesDeclareTablesUniqueConstraintsAndIndexes() {
        Table command = NodeDeleteCommand.class.getAnnotation(Table.class);
        assertThat(command.name()).isEqualTo("node_delete_command");
        assertThat(command.uniqueConstraints())
                .extracting(constraint -> constraint.name())
                .containsExactlyInAnyOrder(
                        "uk_node_delete_command_command_id",
                        "uk_node_delete_command_outbox_id",
                        "uk_node_delete_command_result_event_id"
                );
        assertThat(command.indexes())
                .extracting(index -> index.name())
                .containsExactlyInAnyOrder(
                        "idx_node_delete_command_project_status",
                        "idx_node_delete_command_status_requested_at"
                );

        Table item = NodeDeleteCommandItem.class.getAnnotation(Table.class);
        assertThat(item.name()).isEqualTo("node_delete_command_item");
        assertThat(item.uniqueConstraints())
                .extracting(constraint -> constraint.name())
                .containsExactly("uk_node_delete_command_item_command_node");
        assertThat(item.indexes())
                .extracting(index -> index.name())
                .containsExactly("idx_node_delete_command_item_node");
    }

    @Test
    void itemReferencesOnlyItsPendingCommandAndNotTheProjectionNode() throws Exception {
        ManyToOne commandAssociation = NodeDeleteCommandItem.class
                .getDeclaredField("command")
                .getAnnotation(ManyToOne.class);
        JoinColumn commandJoin = NodeDeleteCommandItem.class
                .getDeclaredField("command")
                .getAnnotation(JoinColumn.class);

        assertThat(commandAssociation).isNotNull();
        assertThat(commandJoin.name()).isEqualTo("node_delete_command_id");
        assertThat(NodeDeleteCommandItem.class.getDeclaredFields())
                .filteredOn(field -> field.getType().equals(ProjectNodeProjection.class))
                .isEmpty();
    }

    @Test
    void entityAndManualDdlUseRequiredIdentifierAndVersionTypes() throws Exception {
        Column nodeId = NodeDeleteCommandItem.class
                .getDeclaredField("nodeId")
                .getAnnotation(Column.class);
        Column expectedNodeVersion = NodeDeleteCommandItem.class
                .getDeclaredField("expectedNodeVersion")
                .getAnnotation(Column.class);
        String ddl = Files.readString(DDL);

        assertThat(nodeId.length()).isEqualTo(36);
        assertThat(expectedNodeVersion).isNotNull();
        assertThat(ddl)
                .contains("id BIGINT NOT NULL AUTO_INCREMENT")
                .contains("node_delete_command_id BIGINT NOT NULL")
                .contains("project_id INT NOT NULL")
                .contains("requested_by_member_id INT NOT NULL")
                .contains("outbox_id INT NULL")
                .contains("expected_graph_version BIGINT NOT NULL")
                .contains("result_graph_version BIGINT NULL")
                .contains("expected_node_version BIGINT NOT NULL")
                .contains("node_id VARCHAR(36) NOT NULL")
                .contains("version BIGINT NOT NULL DEFAULT 0");
    }

    @Test
    void manualDdlDeclaresExpectedConstraintsAndNoProjectionForeignKey() throws Exception {
        String ddl = Files.readString(DDL);

        assertThat(ddl)
                .contains("UNIQUE (command_id)")
                .contains("UNIQUE (outbox_id)")
                .contains("UNIQUE (result_event_id)")
                .contains("UNIQUE (node_delete_command_id, node_id)")
                .contains("idx_node_delete_command_project_status")
                .contains("idx_node_delete_command_status_requested_at")
                .contains("idx_node_delete_command_item_node")
                .contains("FOREIGN KEY (node_delete_command_id) REFERENCES node_delete_command(id)")
                .doesNotContain("REFERENCES project_node_projection");
    }
}
