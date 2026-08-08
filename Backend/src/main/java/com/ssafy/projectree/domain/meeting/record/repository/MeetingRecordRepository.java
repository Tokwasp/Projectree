package com.ssafy.projectree.domain.meeting.record.repository;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface MeetingRecordRepository extends JpaRepository<MeetingRecord, Long> {

    Optional<MeetingRecord> findByMeetingId(int meetingId);

    Optional<MeetingRecord> findByCommandId(String commandId);

    boolean existsByMeetingId(int meetingId);

    boolean existsByCommandId(String commandId);

    @Query("""
        select r
        from MeetingRecord r
        join fetch r.meeting
        where r.meeting.id in :meetingIdList
        """)
    List<MeetingRecord> findByMeetingIdIn(@Param("meetingIdList") List<Integer> meetingIdList);
}
