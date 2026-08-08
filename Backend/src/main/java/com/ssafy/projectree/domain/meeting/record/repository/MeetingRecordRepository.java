package com.ssafy.projectree.domain.meeting.record.repository;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface MeetingRecordRepository extends JpaRepository<MeetingRecord, Long> {

    Optional<MeetingRecord> findByMeetingId(int meetingId);

    Optional<MeetingRecord> findByCommandId(String commandId);

    boolean existsByMeetingId(int meetingId);

    boolean existsByCommandId(String commandId);

    List<MeetingRecord> findByMeetingIdIn(List<Integer> meetingIdList);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingRecord record where record.meeting.project.id = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
