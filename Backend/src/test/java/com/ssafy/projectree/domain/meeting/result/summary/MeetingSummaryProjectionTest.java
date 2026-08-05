package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingSummaryProjectionTest {

    @Test
    void appliesOnlyHigherVersionAndRejectsSameVersionConflicts() {
        MeetingSummaryProjection projection = projection(1, "first");

        assertThat(projection.applyIfNewer(
                "command", payload(0, "older"), Instant.now(), Instant.now()
        )).isFalse();
        assertThat(projection.applyIfNewer(
                "command", payload(1, "first"), Instant.now().plusSeconds(1), Instant.now().plusSeconds(1)
        )).isFalse();
        assertThatThrownBy(() -> projection.applyIfNewer(
                "command", payload(1, "conflict"), Instant.now(), Instant.now()
        )).isInstanceOf(AnalysisResultContractException.class);

        assertThat(projection.applyIfNewer(
                "command", payload(2, "newer"), Instant.now(), Instant.now()
        )).isTrue();
        assertThat(projection.getSummaryVersion()).isEqualTo(2);
    }

    @Test
    void entityDeclaresLatestMeetingUniquenessWithoutDomainAssociationsAndDdlHasNoFks() throws Exception {
        Table table = MeetingSummaryProjection.class.getAnnotation(Table.class);
        assertThat(table.uniqueConstraints()).anySatisfy(constraint ->
                assertThat(constraint.columnNames()).containsExactly("meeting_id")
        );
        for (Field field : MeetingSummaryProjection.class.getDeclaredFields()) {
            assertThat(field.isAnnotationPresent(ManyToOne.class)).isFalse();
            assertThat(field.isAnnotationPresent(OneToOne.class)).isFalse();
        }
        String ddl = Files.readString(Path.of("docs/migrations/20260804_create_meeting_summary_projection.sql"));
        assertThat(ddl)
                .contains("UNIQUE (meeting_id)")
                .doesNotContain("meeting_summary_id CHAR(36) NOT NULL UNIQUE")
                .doesNotContain("FOREIGN KEY")
                .doesNotContain("REFERENCES");
    }

    private MeetingSummaryProjection projection(int version, String suffix) {
        return MeetingSummaryProjection.create(
                1, 1, "command", payload(version, suffix), Instant.now(), Instant.now()
        );
    }

    private MeetingSummaryReadyPayload payload(int version, String suffix) {
        return new MeetingSummaryReadyPayload(
                UUID.nameUUIDFromBytes(suffix.getBytes()).toString(),
                version,
                MeetingSummaryResultStatus.READY,
                "/api/v1/meetings/1/summary?summaryVersion=" + version
        );
    }
}
