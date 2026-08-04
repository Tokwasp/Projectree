package com.ssafy.projectree.domain.meeting.outbox.repository;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface MeetingAnalysisCommandOutboxRepository
        extends JpaRepository<MeetingAnalysisCommandOutbox, Integer> {

    Optional<MeetingAnalysisCommandOutbox> findByMeetingIdAndCommandType(
            int meetingId,
            MeetingAnalysisCommandType commandType
    );

    long countByMeetingId(int meetingId);
}
