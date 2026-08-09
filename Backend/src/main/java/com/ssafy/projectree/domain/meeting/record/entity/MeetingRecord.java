package com.ssafy.projectree.domain.meeting.record.entity;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.Objects;
import java.util.UUID;

/**
 * 회의록 본문의 각 TEXT 컬럼에는 JSON 배열 문자열을 저장한다.
 * DB 컬럼명은 확정 ERD를 따르고, Java 필드명은 저장 형태가 드러나도록 Json 접미사를 붙인다.
 * List&lt;String&gt;과의 변환은 MeetingRecordContentCodec이 담당한다.
 */
@Entity
@Table(
        name = "meeting_record",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_meeting_record_meeting",
                        columnNames = "meeting_id"
                ),
                @UniqueConstraint(
                        name = "uk_meeting_record_command",
                        columnNames = "command_id"
                )
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingRecord extends BaseEntity {

    private static final int MAX_TITLE_LENGTH = 200;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "meeting_record_id")
    private Long id;

    /**
     * Meeting은 회의록의 존재를 알 필요가 없으므로 단방향으로만 참조한다.
     */
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
            name = "meeting_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_meeting_record_meeting")
    )
    private Meeting meeting;

    @Column(
            name = "command_id",
            nullable = false,
            length = 36,
            columnDefinition = "CHAR(36)"
    )
    private String commandId;

    @Column(nullable = false, length = MAX_TITLE_LENGTH)
    private String title;

    @Column(name = "summary", columnDefinition = "TEXT")
    private String summaryJson;

    @Column(name = "decisions", columnDefinition = "TEXT")
    private String decisionsJson;

    @Column(name = "next_todos", columnDefinition = "TEXT")
    private String nextTodosJson;

    @Column(name = "issues", columnDefinition = "TEXT")
    private String issuesJson;

    @Version
    @Column(nullable = false)
    private long version;

    public static MeetingRecord create(
            Meeting meeting,
            UUID commandId,
            String title,
            String summaryJson,
            String decisionsJson,
            String nextTodosJson,
            String issuesJson
    ) {
        MeetingRecord record = new MeetingRecord();
        record.meeting = Objects.requireNonNull(meeting, "meeting must not be null");
        record.commandId = Objects.requireNonNull(commandId, "commandId must not be null").toString();
        record.title = validateTitle(title);
        record.summaryJson = summaryJson;
        record.decisionsJson = decisionsJson;
        record.nextTodosJson = nextTodosJson;
        record.issuesJson = issuesJson;
        return record;
    }

    /**
     * 사용자 수정은 본문 전체를 교체한다.
     * meeting과 commandId는 생성 이후 변경하지 않으며 version은 JPA가 관리한다.
     */
    public void update(
            String title,
            String summaryJson,
            String decisionsJson,
            String nextTodosJson,
            String issuesJson
    ) {
        this.title = validateTitle(title);
        this.summaryJson = summaryJson;
        this.decisionsJson = decisionsJson;
        this.nextTodosJson = nextTodosJson;
        this.issuesJson = issuesJson;
    }

    private static String validateTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title must not be null or blank");
        }
        if (title.length() > MAX_TITLE_LENGTH) {
            throw new IllegalArgumentException("title must be 200 characters or fewer");
        }
        return title;
    }
}
