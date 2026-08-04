package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
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
    private final ProjectMemberRepository projectMemberRepository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public MeetingSynchronizationOutcome synchronize(MeetingRoomRedisEntry entry) {
        Meeting existingMeeting = meetingRepository
                .findByRoomNameForUpdate(entry.roomName())
                .orElse(null);
        if (existingMeeting != null) {
            if (existingMeeting.getProject().getId() != entry.projectId()) {
                return MeetingSynchronizationOutcome.CREATOR_CONFLICT;
            }
            if (existingMeeting.getCreatorMemberId() != null) {
                return existingMeeting.getCreatorMemberId().equals(entry.creatorMemberId())
                        ? MeetingSynchronizationOutcome.ALREADY_EXISTS
                        : MeetingSynchronizationOutcome.CREATOR_CONFLICT;
            }
        }

        Project project = projectRepository.findById(entry.projectId()).orElse(null);
        if (project == null) {
            return MeetingSynchronizationOutcome.PROJECT_NOT_FOUND;
        }

        ProjectMember creatorProjectMember = projectMemberRepository
                .findByProjectIdAndMemberId(entry.projectId(), entry.creatorMemberId())
                .orElse(null);
        if (creatorProjectMember == null) {
            return MeetingSynchronizationOutcome.CREATOR_PROJECT_MEMBER_NOT_FOUND;
        }

        if (existingMeeting != null) {
            try {
                boolean registered = existingMeeting.registerCreator(creatorProjectMember);
                return registered
                        ? MeetingSynchronizationOutcome.CREATOR_REGISTERED
                        : MeetingSynchronizationOutcome.ALREADY_EXISTS;
            } catch (IllegalArgumentException | IllegalStateException exception) {
                return MeetingSynchronizationOutcome.CREATOR_CONFLICT;
            }
        }

        meetingRepository.saveAndFlush(
                Meeting.create(project, creatorProjectMember, entry.roomName())
        );
        return MeetingSynchronizationOutcome.CREATED;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW, readOnly = true)
    public boolean existsByRoomName(String roomName) {
        return meetingRepository.existsByRoomName(roomName);
    }
}
