package com.ssafy.projectree.domain.meeting.outbox;

import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingAnalysisCommandOutboxSchemaTest {
    @Test
    void entityDeclaresPublisherIndex() {
        Table table = MeetingAnalysisCommandOutbox.class.getAnnotation(Table.class);
        assertThat(table).isNotNull();
        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_analysis_outbox_publish");
            assertThat(index.columnList()).isEqualTo("status, created_at, id");
        });
    }

    @Test
    void manualDdlDeclaresPublisherIndex() throws Exception {
        String ddl = Files.readString(Path.of("docs/migrations/20260804_create_meeting_analysis_command_outbox.sql"));
        assertThat(ddl).contains("idx_meeting_analysis_outbox_publish");
        assertThat(ddl).contains("(status, created_at, id)");
    }
}
