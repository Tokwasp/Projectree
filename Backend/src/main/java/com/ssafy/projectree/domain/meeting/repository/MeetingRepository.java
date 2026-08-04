package com.ssafy.projectree.domain.meeting.repository;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface MeetingRepository extends JpaRepository<Meeting, Integer> {

    boolean existsByRoomName(String roomName);

    Optional<Meeting> findByRoomName(String roomName);
}
