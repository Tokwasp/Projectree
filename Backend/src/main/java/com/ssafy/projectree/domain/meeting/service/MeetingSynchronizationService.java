package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

import java.util.Locale;

@Slf4j
@Service
@RequiredArgsConstructor
public class MeetingSynchronizationService {

    private static final String ROOM_NAME_UNIQUE_CONSTRAINT = "uk_meeting_room_name";

    private final MeetingSynchronizationWriter writer;

    public MeetingSynchronizationOutcome synchronize(MeetingRoomRedisEntry entry) {
        if (!isValid(entry)) {
            log.warn("[MeetingSync] Invalid synchronization entry. key={}", entry == null ? null : entry.sourceKey());
            return MeetingSynchronizationOutcome.INVALID_ENTRY;
        }

        try {
            MeetingSynchronizationOutcome outcome = writer.synchronize(entry);
            if (outcome == MeetingSynchronizationOutcome.PROJECT_NOT_FOUND) {
                log.warn(
                        "[MeetingSync] PROJECT_NOT_FOUND. projectId={}, roomName={}",
                        entry.projectId(),
                        entry.roomName()
                );
            }
            return outcome;
        } catch (DataIntegrityViolationException exception) {
            return absorbConcurrentRoomNameInsert(entry, exception);
        }
    }

    private MeetingSynchronizationOutcome absorbConcurrentRoomNameInsert(
            MeetingRoomRedisEntry entry,
            DataIntegrityViolationException exception
    ) {
        if (!isRoomNameUniqueViolation(exception) || !writer.existsByRoomName(entry.roomName())) {
            throw exception;
        }

        log.debug(
                "[MeetingSync] Concurrent roomName insert was already completed. roomName={}",
                entry.roomName()
        );
        return MeetingSynchronizationOutcome.UNIQUE_COLLISION;
    }

    private boolean isRoomNameUniqueViolation(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof ConstraintViolationException violation) {
                String constraintName = violation.getConstraintName();
                if (constraintName != null && !constraintName.isBlank()) {
                    return isRoomNameConstraintName(constraintName);
                }
            }
            current = current.getCause();
        }

        return containsRoomNameConstraintInMessage(throwable);
    }

    private boolean isRoomNameConstraintName(String constraintName) {
        String normalized = constraintName
                .replace("\"", "")
                .replace("`", "")
                .toLowerCase(Locale.ROOT);
        int schemaSeparator = normalized.lastIndexOf('.');
        if (schemaSeparator >= 0) {
            normalized = normalized.substring(schemaSeparator + 1);
        }
        return normalized.equals(ROOM_NAME_UNIQUE_CONSTRAINT)
                || normalized.startsWith(ROOM_NAME_UNIQUE_CONSTRAINT + "_index_");
    }

    private boolean containsRoomNameConstraintInMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            String message = current.getMessage();
            if (message != null
                    && message.toLowerCase(Locale.ROOT).contains(ROOM_NAME_UNIQUE_CONSTRAINT)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private boolean isValid(MeetingRoomRedisEntry entry) {
        return entry != null
                && entry.projectId() != null
                && entry.projectId() > 0
                && entry.roomName() != null
                && !entry.roomName().isBlank();
    }
}
