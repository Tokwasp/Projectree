package com.ssafy.projectree.domain.meeting.result.inbox;

import com.ssafy.projectree.domain.meeting.result.inbox.entity.MeetingAnalysisResultInbox;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingAnalysisResultInboxSchemaTest {

    @Test
    void entityDeclaresEventIdUniquenessAndLookupIndexesWithoutDomainAssociations() {
        Table table = MeetingAnalysisResultInbox.class.getAnnotation(Table.class);

        assertThat(table.uniqueConstraints()).anySatisfy(constraint -> {
            assertThat(constraint.name()).isEqualTo("uk_meeting_analysis_result_event_id");
            assertThat(constraint.columnNames()).containsExactly("event_id");
        });
        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_analysis_result_command");
            assertThat(index.columnList()).isEqualTo("command_id");
        });
        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_analysis_result_meeting");
            assertThat(index.columnList()).isEqualTo("meeting_id, processed_at");
        });
        for (Field field : MeetingAnalysisResultInbox.class.getDeclaredFields()) {
            assertThat(field.isAnnotationPresent(ManyToOne.class)).isFalse();
            assertThat(field.isAnnotationPresent(OneToOne.class)).isFalse();
        }
    }

    @Test
    void manualDdlHasNoProjectMeetingOrOutboxForeignKey() throws Exception {
        String ddl = Files.readString(Path.of(
                "docs/migrations/20260804_create_meeting_analysis_result_inbox.sql"
        ));

        assertThat(ddl)
                .contains("event_id CHAR(36) NOT NULL")
                .contains("UNIQUE (event_id)")
                .contains("idx_meeting_analysis_result_command")
                .contains("idx_meeting_analysis_result_meeting")
                .doesNotContain("FOREIGN KEY")
                .doesNotContain("REFERENCES");
    }
}
