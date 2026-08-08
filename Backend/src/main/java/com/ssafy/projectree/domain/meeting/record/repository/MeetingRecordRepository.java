package com.ssafy.projectree.domain.meeting.record.repository;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
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

    List<MeetingRecord> findByMeetingIdIn(List<Integer> meetingIdList);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingRecord record where record.meeting.project.id = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);

    @Query("""
        select r
        from MeetingRecord r
        join fetch r.meeting m
        where m.project.id = :projectId
        order by r.createdAt desc, r.id desc
        limit 5
        """)
    List<MeetingRecord> findRecentFiveByProjectId(@Param("projectId") int projectId);
}
