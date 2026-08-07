package com.ssafy.projectree.domain.meeting.result.graph;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import jakarta.persistence.Column;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectGraphProjectionSchemaTest {

    @Test
    void projectionEntitiesUseScalarRelationshipsAndDeclareReadIndexes() {
        assertThat(ProjectGraphSync.class.getAnnotation(Table.class).name()).isEqualTo("project_graph_sync");
        assertThat(ProjectNodeProjection.class.getAnnotation(Table.class).indexes())
                .extracting(index -> index.name())
                .contains("idx_project_node_tree", "idx_project_node_parent", "idx_project_node_merged_target");
        assertThat(NodeEvidenceProjection.class.getAnnotation(Table.class).indexes())
                .extracting(index -> index.name())
                .contains("idx_node_evidence_order", "idx_node_evidence_meeting");
        for (Class<?> type : List.of(ProjectNodeProjection.class, NodeEvidenceProjection.class)) {
            for (Field field : type.getDeclaredFields()) {
                assertThat(field.isAnnotationPresent(ManyToOne.class)).isFalse();
                assertThat(field.isAnnotationPresent(OneToOne.class)).isFalse();
            }
        }
    }

    @Test
    void manualDdlHasOnlyTheInternalEvidenceToProjectionNodeForeignKey() throws Exception {
        String ddl = Files.readString(Path.of("docs/migrations/20260804_create_project_graph_projection.sql"));

        assertThat(ddl)
                .contains("CREATE TABLE project_graph_sync")
                .contains("CREATE TABLE project_node_projection")
                .contains("CREATE TABLE node_evidence_projection")
                .contains("FOREIGN KEY (node_id) REFERENCES project_node_projection(node_id)")
                .doesNotContain("node_merge_projection")
                .doesNotContain("project_id) REFERENCES")
                .doesNotContain("meeting_id) REFERENCES");
    }

    @Test
    void nodeContentUsesMediumText() throws Exception {
        Column content = ProjectNodeProjection.class
                .getDeclaredField("content")
                .getAnnotation(Column.class);

        assertThat(content.columnDefinition()).isEqualTo("MEDIUMTEXT");
    }
}
