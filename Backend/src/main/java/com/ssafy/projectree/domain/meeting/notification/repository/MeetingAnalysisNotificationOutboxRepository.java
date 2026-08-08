package com.ssafy.projectree.domain.meeting.notification.repository;

import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MeetingAnalysisNotificationOutboxRepository
        extends JpaRepository<MeetingAnalysisNotificationOutbox, Integer> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingAnalysisNotificationOutbox outbox where outbox.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
