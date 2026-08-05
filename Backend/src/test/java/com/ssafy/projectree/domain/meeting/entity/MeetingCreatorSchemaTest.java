package com.ssafy.projectree.domain.meeting.entity;

import jakarta.persistence.Column;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingCreatorSchemaTest {

    @Test
    void creatorIsStoredAsNullableMemberIdWithoutJpaAssociation() throws Exception {
        Field creatorMemberId = Meeting.class.getDeclaredField("creatorMemberId");

        assertThat(creatorMemberId.getType()).isEqualTo(Integer.class);
        assertThat(creatorMemberId.getAnnotation(ManyToOne.class)).isNull();
        assertThat(creatorMemberId.getAnnotation(Column.class).name())
                .isEqualTo("creator_member_id");
    }

    @Test
    void entityDeclaresProjectCreatorIndex() {
        Table table = Meeting.class.getAnnotation(Table.class);

        assertThat(table.indexes()).anySatisfy(index -> {
            assertThat(index.name()).isEqualTo("idx_meeting_project_creator");
            assertThat(index.columnList()).isEqualTo("project_id, creator_member_id");
        });
    }

    @Test
    void migrationDoesNotCoupleCreatorToProjectMemberLifecycle() throws Exception {
        String ddl = Files.readString(Path.of(
                "docs/migrations/20260804_add_meeting_creator_member.sql"
        ));

        assertThat(ddl)
                .contains("creator_member_id INT NULL")
                .contains("idx_meeting_project_creator")
                .contains("(project_id, creator_member_id)")
                .doesNotContain("creator_project_member_id")
                .doesNotContain("REFERENCES project_member");
    }
}
