package com.ssafy.projectree.domain.meeting.notification.repository;

import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MeetingAnalysisNotificationOutboxRepository
        extends JpaRepository<MeetingAnalysisNotificationOutbox, Integer> {
}
