package com.ssafy.projectree.domain.meeting.result.inbox.repository;

import com.ssafy.projectree.domain.meeting.result.inbox.entity.MeetingAnalysisResultInbox;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MeetingAnalysisResultInboxRepository
        extends JpaRepository<MeetingAnalysisResultInbox, Long> {

    boolean existsByEventId(String eventId);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingAnalysisResultInbox inbox where inbox.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
