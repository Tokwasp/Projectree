package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class MeetingSynchronizationWriter {

    private final MeetingRepository meetingRepository;
    private final ProjectRepository projectRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public MeetingSynchronizationOutcome synchronize(MeetingRoomRedisEntry entry) {
        if (meetingRepository.existsByRoomName(entry.roomName())) {
            return MeetingSynchronizationOutcome.ALREADY_EXISTS;
        }

        Project project = projectRepository.findById(entry.projectId()).orElse(null);
        if (project == null) {
            return MeetingSynchronizationOutcome.PROJECT_NOT_FOUND;
        }

        meetingRepository.saveAndFlush(Meeting.create(project, entry.roomName()));
        return MeetingSynchronizationOutcome.CREATED;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
    public boolean existsByRoomName(String roomName) {
        return meetingRepository.existsByRoomName(roomName);
    }
}
