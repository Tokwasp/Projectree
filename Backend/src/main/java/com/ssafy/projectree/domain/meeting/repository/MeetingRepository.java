package com.ssafy.projectree.domain.meeting.repository;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface MeetingRepository extends JpaRepository<Meeting, Integer> {

    @Query("""
            select m
            from Meeting m
            where m.project.id = :projectId
            order by m.createdAt desc
            limit 5
            """)
    List<Meeting> findRecentFiveBy(@Param("projectId") int projectId);

    boolean existsByRoomName(String roomName);

    boolean existsByProjectId(int projectId);

    Optional<Meeting> findByRoomName(String roomName);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select m
            from Meeting m
            where m.roomName = :roomName
            """)
    Optional<Meeting> findByRoomNameForUpdate(@Param("roomName") String roomName);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select m
            from Meeting m
            where m.project.id = :projectId
              and m.roomName = :roomName
            """)
    Optional<Meeting> findByProjectIdAndRoomNameForUpdate(
            @Param("projectId") int projectId,
            @Param("roomName") String roomName
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select m
            from Meeting m
            where m.id = :meetingId
            """)
    Optional<Meeting> findByIdForUpdate(@Param("meetingId") int meetingId);

    @Query("""
            select m
            from Meeting m
            join fetch m.project
            where m.id = :meetingId
            """)
    Optional<Meeting> findByIdWithProject(@Param("meetingId") int meetingId);
}
