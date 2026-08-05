package com.ssafy.projectree.domain.meeting.record;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import jakarta.persistence.Column;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;

class MeetingRecordSchemaTest {

    private static final Path DDL_PATH =
            Path.of("docs/migrations/20260805_create_meeting_record.sql");

    @DisplayName("테이블명과 두 UNIQUE 제약 이름을 선언한다.")
    @Test
    void entityDeclaresTableAndUniqueConstraints() {
        Table table = MeetingRecord.class.getAnnotation(Table.class);

        assertThat(table).isNotNull();
        assertThat(table.name()).isEqualTo("meeting_record");
        assertThat(table.uniqueConstraints()).anySatisfy(constraint -> {
            assertThat(constraint.name()).isEqualTo("uk_meeting_record_meeting");
            assertThat(constraint.columnNames()).containsExactly("meeting_id");
        });
        assertThat(table.uniqueConstraints()).anySatisfy(constraint -> {
            assertThat(constraint.name()).isEqualTo("uk_meeting_record_command");
            assertThat(constraint.columnNames()).containsExactly("command_id");
        });
    }

    @DisplayName("PK는 BIGINT에 대응하는 Long이고 컬럼명은 meeting_record_id다.")
    @Test
    void primaryKeyIsLong() throws Exception {
        Field id = MeetingRecord.class.getDeclaredField("id");

        assertThat(id.getType()).isEqualTo(Long.class);
        assertThat(id.getAnnotation(Column.class).name()).isEqualTo("meeting_record_id");
    }

    @DisplayName("Meeting은 LAZY 단방향 OneToOne으로 참조하고 FK 이름을 지정한다.")
    @Test
    void meetingIsLazyUnidirectionalOneToOne() throws Exception {
        Field meeting = MeetingRecord.class.getDeclaredField("meeting");
        OneToOne oneToOne = meeting.getAnnotation(OneToOne.class);
        JoinColumn joinColumn = meeting.getAnnotation(JoinColumn.class);

        assertThat(meeting.getType()).isEqualTo(Meeting.class);
        assertThat(oneToOne).isNotNull();
        assertThat(oneToOne.fetch()).isEqualTo(FetchType.LAZY);
        assertThat(oneToOne.optional()).isFalse();
        assertThat(oneToOne.mappedBy()).isEmpty();
        assertThat(joinColumn.name()).isEqualTo("meeting_id");
        assertThat(joinColumn.nullable()).isFalse();
        assertThat(joinColumn.foreignKey())
                .extracting(ForeignKey::name)
                .isEqualTo("fk_meeting_record_meeting");
    }

    @DisplayName("commandId는 CHAR(36) 컬럼으로 선언한다.")
    @Test
    void commandIdIsFixedLengthChar() throws Exception {
        Column commandId = MeetingRecord.class.getDeclaredField("commandId").getAnnotation(Column.class);

        assertThat(commandId.name()).isEqualTo("command_id");
        assertThat(commandId.nullable()).isFalse();
        assertThat(commandId.length()).isEqualTo(36);
        assertThat(commandId.columnDefinition()).isEqualTo("CHAR(36)");
    }

    @DisplayName("본문 네 필드는 확정 ERD 컬럼명을 가진 TEXT 컬럼이다.")
    @ParameterizedTest
    @CsvSource({
            "summaryJson, summary",
            "decisionsJson, decisions",
            "nextTodosJson, next_todos",
            "issuesJson, issues"
    })
    void contentFieldsAreTextColumns(String fieldName, String columnName) throws Exception {
        Column column = MeetingRecord.class.getDeclaredField(fieldName).getAnnotation(Column.class);

        assertThat(column.name()).isEqualTo(columnName);
        assertThat(column.columnDefinition()).isEqualTo("TEXT");
    }

    @DisplayName("낙관적 락 버전 필드에 @Version이 존재한다.")
    @Test
    void versionFieldIsManagedByJpa() throws Exception {
        Field version = MeetingRecord.class.getDeclaredField("version");

        assertThat(version.getAnnotation(Version.class)).isNotNull();
        assertThat(version.getType()).isEqualTo(long.class);
        assertThat(version.getAnnotation(Column.class).nullable()).isFalse();
    }

    @DisplayName("감사 시각은 BaseEntity에서 상속받고 중복 선언하지 않는다.")
    @Test
    void auditingFieldsComeFromBaseEntity() {
        assertThat(MeetingRecord.class.getSuperclass().getSimpleName()).isEqualTo("BaseEntity");
        assertThat(MeetingRecord.class.getDeclaredFields())
                .extracting(Field::getName)
                .doesNotContain("createdAt", "updatedAt");
    }

    @DisplayName("Meeting에는 MeetingRecord 역방향 필드를 추가하지 않는다.")
    @Test
    void meetingHasNoReverseAssociation() {
        assertThat(Arrays.stream(Meeting.class.getDeclaredFields())
                .map(Field::getType)
                .toList())
                .doesNotContain(MeetingRecord.class);
        assertThat(Meeting.class.getDeclaredFields())
                .extracting(Field::getName)
                .doesNotContain("meetingRecord", "record");
    }

    @DisplayName("수동 DDL이 확정 컬럼 타입과 제약을 선언한다.")
    @Test
    void manualDdlDeclaresColumnsAndConstraints() throws Exception {
        String ddl = Files.readString(DDL_PATH);

        assertThat(ddl)
                .contains("CREATE TABLE meeting_record")
                .contains("meeting_record_id BIGINT NOT NULL AUTO_INCREMENT")
                .contains("meeting_id INT NOT NULL")
                .contains("command_id CHAR(36) NOT NULL")
                .contains("title VARCHAR(200) NOT NULL")
                .contains("summary TEXT NULL")
                .contains("decisions TEXT NULL")
                .contains("next_todos TEXT NULL")
                .contains("issues TEXT NULL")
                .contains("created_at DATETIME(6) NOT NULL")
                .contains("updated_at DATETIME(6) NOT NULL")
                .contains("version BIGINT NOT NULL DEFAULT 0")
                .contains("PRIMARY KEY (meeting_record_id)")
                .contains("uk_meeting_record_meeting")
                .contains("UNIQUE (meeting_id)")
                .contains("uk_meeting_record_command")
                .contains("UNIQUE (command_id)")
                .contains("fk_meeting_record_meeting")
                .contains("FOREIGN KEY (meeting_id)")
                .contains("REFERENCES meeting (id)");
    }

    @DisplayName("수동 DDL은 파생 가능한 시간 정보와 중복 컬럼을 저장하지 않는다.")
    @Test
    void manualDdlDoesNotDuplicateMeetingColumns() throws Exception {
        String ddl = Files.readString(DDL_PATH);

        assertThat(ddl)
                .doesNotContain("project_id")
                .doesNotContain("room_name")
                .doesNotContain("started_at")
                .doesNotContain("ended_at")
                .doesNotContain("duration")
                .doesNotContain("ON DELETE");
    }

    @DisplayName("수동 DDL 파일이 확정 경로에 존재한다.")
    @Test
    void ddlFileExists() {
        assertThat(DDL_PATH).exists();
    }
}
