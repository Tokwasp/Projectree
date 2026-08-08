package com.ssafy.projectree.domain.meeting.result.summary.repository;

import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface MeetingSummaryProjectionRepository
        extends JpaRepository<MeetingSummaryProjection, Long> {

    Optional<MeetingSummaryProjection> findByMeetingId(int meetingId);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingSummaryProjection projection where projection.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
