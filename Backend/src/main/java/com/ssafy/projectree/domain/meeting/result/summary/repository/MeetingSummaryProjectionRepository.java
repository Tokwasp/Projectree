package com.ssafy.projectree.domain.meeting.result.summary.repository;

import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface MeetingSummaryProjectionRepository
        extends JpaRepository<MeetingSummaryProjection, Long> {

    Optional<MeetingSummaryProjection> findByMeetingId(int meetingId);
}
