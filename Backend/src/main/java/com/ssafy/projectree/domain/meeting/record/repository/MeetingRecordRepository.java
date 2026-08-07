package com.ssafy.projectree.domain.meeting.record.repository;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface MeetingRecordRepository extends JpaRepository<MeetingRecord, Long> {

    Optional<MeetingRecord> findByMeetingId(int meetingId);

    Optional<MeetingRecord> findByCommandId(String commandId);

    @Query(
            value = """
                    select record
                    from MeetingRecord record
                    join fetch record.meeting meeting
                    where meeting.project.id = :projectId
                    """,
            countQuery = """
                    select count(record)
                    from MeetingRecord record
                    join record.meeting meeting
                    where meeting.project.id = :projectId
                    """
    )
    Page<MeetingRecord> findPageByProjectId(
            @Param("projectId") int projectId,
            Pageable pageable
    );

    boolean existsByMeetingId(int meetingId);

    boolean existsByCommandId(String commandId);
}
