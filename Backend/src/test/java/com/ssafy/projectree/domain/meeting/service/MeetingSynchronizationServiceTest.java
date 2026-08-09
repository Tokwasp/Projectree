package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.hibernate.exception.ConstraintViolationException;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import java.sql.SQLException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingSynchronizationServiceTest {

    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";

    @Mock
    private MeetingSynchronizationWriter writer;

    private MeetingSynchronizationService service;

    @BeforeEach
    void setUp() {
        service = new MeetingSynchronizationService(writer);
    }

    @DisplayName("유효한 entry는 독립 트랜잭션 Writer에 위임한다.")
    @Test
    void delegatesValidEntry() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        when(writer.synchronize(entry)).thenReturn(MeetingSynchronizationOutcome.CREATED);

        assertThat(service.synchronize(entry)).isEqualTo(MeetingSynchronizationOutcome.CREATED);
    }

    @DisplayName("null 또는 필수 값이 잘못된 entry는 저장하지 않는다.")
    @Test
    void rejectsInvalidEntry() {
        assertThat(service.synchronize(null)).isEqualTo(MeetingSynchronizationOutcome.INVALID_ENTRY);
        assertThat(service.synchronize(entry(0, ROOM_NAME)))
                .isEqualTo(MeetingSynchronizationOutcome.INVALID_ENTRY);
        assertThat(service.synchronize(entry(1, " ")))
                .isEqualTo(MeetingSynchronizationOutcome.INVALID_ENTRY);

        verify(writer, never()).synchronize(org.mockito.ArgumentMatchers.any());
    }

    @DisplayName("roomName UNIQUE 충돌 후 실제 row가 존재하면 정상 중복으로 흡수한다.")
    @Test
    void absorbsRoomNameUniqueViolationAfterWriterTransactionEnds() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException collision = new DataIntegrityViolationException(
                "constraint [uk_meeting_room_name]"
        );
        when(writer.synchronize(entry)).thenThrow(collision);
        when(writer.existsByRoomName(ROOM_NAME)).thenReturn(true);

        assertThat(service.synchronize(entry))
                .isEqualTo(MeetingSynchronizationOutcome.UNIQUE_COLLISION);

        verify(writer).existsByRoomName(ROOM_NAME);
    }

    @DisplayName("roomName UNIQUE가 아닌 무결성 오류는 숨기지 않는다.")
    @Test
    void rethrowsOtherIntegrityViolation() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException foreignKeyViolation = new DataIntegrityViolationException(
                "constraint [fk_meeting_project]"
        );
        when(writer.synchronize(entry)).thenThrow(foreignKeyViolation);

        assertThatThrownBy(() -> service.synchronize(entry)).isSameAs(foreignKeyViolation);
        verify(writer, never()).existsByRoomName(ROOM_NAME);
    }

    @DisplayName("UNIQUE 메시지여도 실제 row가 없으면 오류를 숨기지 않는다.")
    @Test
    void rethrowsUniqueViolationWhenMeetingIsNotPresent() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException collision = new DataIntegrityViolationException(
                "constraint [uk_meeting_room_name]"
        );
        when(writer.synchronize(entry)).thenThrow(collision);
        when(writer.existsByRoomName(ROOM_NAME)).thenReturn(false);

        assertThatThrownBy(() -> service.synchronize(entry)).isSameAs(collision);
    }

    @DisplayName("Hibernate가 제공한 roomName constraintName을 메시지보다 우선 사용한다.")
    @Test
    void identifiesHibernateConstraintName() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException collision = integrityViolation(
                "unrelated outer message",
                "uk_meeting_room_name",
                "unrelated hibernate message"
        );
        when(writer.synchronize(entry)).thenThrow(collision);
        when(writer.existsByRoomName(ROOM_NAME)).thenReturn(true);

        assertThat(service.synchronize(entry))
                .isEqualTo(MeetingSynchronizationOutcome.UNIQUE_COLLISION);
    }

    @DisplayName("Hibernate constraintName이 null이면 메시지를 fallback으로 검사한다.")
    @Test
    void fallsBackToMessageWhenConstraintNameIsNull() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException collision = integrityViolation(
                "could not execute statement",
                null,
                "constraint [UK_MEETING_ROOM_NAME]"
        );
        when(writer.synchronize(entry)).thenThrow(collision);
        when(writer.existsByRoomName(ROOM_NAME)).thenReturn(true);

        assertThat(service.synchronize(entry))
                .isEqualTo(MeetingSynchronizationOutcome.UNIQUE_COLLISION);
    }

    @DisplayName("다른 Hibernate constraintName은 메시지에 roomName 문자열이 있어도 삼키지 않는다.")
    @Test
    void doesNotFallbackWhenDifferentConstraintNameIsAvailable() {
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        DataIntegrityViolationException violation = integrityViolation(
                "uk_meeting_room_name",
                "fk_meeting_project",
                "uk_meeting_room_name"
        );
        when(writer.synchronize(entry)).thenThrow(violation);

        assertThatThrownBy(() -> service.synchronize(entry)).isSameAs(violation);
        verify(writer, never()).existsByRoomName(ROOM_NAME);
    }

    private DataIntegrityViolationException integrityViolation(
            String outerMessage,
            String constraintName,
            String hibernateMessage
    ) {
        ConstraintViolationException hibernateException = new ConstraintViolationException(
                hibernateMessage,
                new SQLException(hibernateMessage),
                (String) null,
                constraintName
        );
        return new DataIntegrityViolationException(outerMessage, hibernateException);
    }

    private MeetingRoomRedisEntry entry(int projectId, String roomName) {
        return new MeetingRoomRedisEntry(
                "meeting:project:" + projectId,
                projectId,
                722,
                roomName
        );
    }
}
