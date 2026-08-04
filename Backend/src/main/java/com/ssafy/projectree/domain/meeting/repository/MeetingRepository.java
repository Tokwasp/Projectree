package com.ssafy.projectree.domain.meeting.repository;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface MeetingRepository extends JpaRepository<Meeting, Integer> {

    boolean existsByRoomName(String roomName);

    Optional<Meeting> findByRoomName(String roomName);

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
}
