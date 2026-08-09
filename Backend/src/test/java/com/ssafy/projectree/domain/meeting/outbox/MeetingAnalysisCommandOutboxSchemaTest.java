package com.ssafy.projectree.domain.meeting.outbox;

import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import jakarta.persistence.Table;
import jakarta.persistence.JoinColumn;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingAnalysisCommandOutboxSchemaTest {
    @Test
    void entityDeclaresClaimIndexes() {
        Table table = MeetingAnalysisCommandOutbox.class.getAnnotation(Table.class);
        assertThat(table).isNotNull();
        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_analysis_outbox_pending");
            assertThat(index.columnList()).isEqualTo("status, next_attempt_at, created_at, id");
        });
        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_analysis_outbox_expired_lease");
            assertThat(index.columnList()).isEqualTo("status, lease_until, created_at, id");
        });
    }

    @Test
    void meetingAssociationAndManualDdlAreNullableForNodeCommands() throws Exception {
        JoinColumn meetingColumn = MeetingAnalysisCommandOutbox.class
                .getDeclaredField("meeting")
                .getAnnotation(JoinColumn.class);
        String ddl = Files.readString(Path.of(
                "docs/migrations/20260804_create_meeting_analysis_command_outbox.sql"
        ));

        assertThat(meetingColumn.nullable()).isTrue();
        assertThat(ddl)
                .contains("meeting_id INT NULL")
                .contains("target_project_id INT NULL")
                .contains("target_node_id VARCHAR(36) NULL")
                .contains("UNIQUE (meeting_id, command_type)");
    }

    @Test
    void manualDdlDeclaresClaimIndexesAndMetadataColumns() throws Exception {
        String ddl = Files.readString(Path.of("docs/migrations/20260804_create_meeting_analysis_command_outbox.sql"));
        assertThat(ddl)
                .contains("requested_by_member_id INT NOT NULL")
                .contains("next_attempt_at DATETIME(6)")
                .contains("lease_until DATETIME(6)")
                .contains("claim_token VARCHAR(36)")
                .contains("idx_meeting_analysis_outbox_pending")
                .contains("(status, next_attempt_at, created_at, id)")
                .contains("idx_meeting_analysis_outbox_expired_lease")
                .contains("(status, lease_until, created_at, id)");
    }

    @Test
    void notificationDdlDeclaresIdAndBusinessUniqueness() throws Exception {
        String ddl = Files.readString(Path.of(
                "docs/migrations/20260804_create_meeting_analysis_notification_outbox.sql"
        ));
        assertThat(ddl)
                .contains("UNIQUE (notification_id)")
                .contains("UNIQUE (command_id, audience, notification_type)")
                .contains("recipient_member_id INT NULL");
    }
}
