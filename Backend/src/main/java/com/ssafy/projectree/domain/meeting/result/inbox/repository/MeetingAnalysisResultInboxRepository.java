package com.ssafy.projectree.domain.meeting.result.inbox.repository;

import com.ssafy.projectree.domain.meeting.result.inbox.entity.MeetingAnalysisResultInbox;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MeetingAnalysisResultInboxRepository
        extends JpaRepository<MeetingAnalysisResultInbox, Long> {

    boolean existsByEventId(String eventId);
}
