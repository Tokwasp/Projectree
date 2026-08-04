package com.ssafy.projectree.domain.meeting.result.inbox.service;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.DuplicateAnalysisResultEventException;
import com.ssafy.projectree.domain.meeting.result.inbox.entity.MeetingAnalysisResultInbox;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import lombok.RequiredArgsConstructor;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.util.Locale;

@Service
@RequiredArgsConstructor
public class ResultInboxService {

    private static final String EVENT_ID_UNIQUE_CONSTRAINT = "uk_meeting_analysis_result_event_id";

    private final MeetingAnalysisResultInboxRepository inboxRepository;
    private final Clock clock;

    @Transactional(readOnly = true)
    public boolean isProcessed(String eventId) {
        return inboxRepository.existsByEventId(eventId);
    }

    @Transactional
    public void registerProcessed(AnalysisResultEventEnvelope event) {
        try {
            inboxRepository.saveAndFlush(
                    MeetingAnalysisResultInbox.processed(event, Instant.now(clock))
            );
        } catch (DataIntegrityViolationException exception) {
            if (isEventIdUniqueViolation(exception)) {
                throw new DuplicateAnalysisResultEventException(event.eventId(), exception);
            }
            throw exception;
        }
    }

    private boolean isEventIdUniqueViolation(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof ConstraintViolationException violation) {
                String constraintName = violation.getConstraintName();
                if (constraintName != null && !constraintName.isBlank()) {
                    String normalized = normalizedConstraintName(constraintName);
                    return normalized.equals(EVENT_ID_UNIQUE_CONSTRAINT)
                            || normalized.startsWith(EVENT_ID_UNIQUE_CONSTRAINT + "_index_");
                }
            }
            current = current.getCause();
        }

        current = throwable;
        while (current != null) {
            String message = current.getMessage();
            if (message != null && message.toLowerCase(Locale.ROOT)
                    .contains(EVENT_ID_UNIQUE_CONSTRAINT)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private String normalizedConstraintName(String constraintName) {
        String normalized = constraintName.replace("\"", "").replace("`", "")
                .toLowerCase(Locale.ROOT);
        int schemaSeparator = normalized.lastIndexOf('.');
        return schemaSeparator >= 0 ? normalized.substring(schemaSeparator + 1) : normalized;
    }
}
