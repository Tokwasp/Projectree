package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingSynchronizationWriterTest {

    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";

    @Mock
    private MeetingRepository meetingRepository;

    @Mock
    private ProjectRepository projectRepository;

    private MeetingSynchronizationWriter writer;

    @BeforeEach
    void setUp() {
        writer = new MeetingSynchronizationWriter(meetingRepository, projectRepository);
    }

    @DisplayName("Project가 존재하고 roomName이 신규이면 Meeting을 저장한다.")
    @Test
    void createsNewMeeting() {
        Project project = Project.builder().title("project").content("content").build();
        MeetingRoomRedisEntry entry = entry(1, ROOM_NAME);
        when(meetingRepository.existsByRoomName(ROOM_NAME)).thenReturn(false);
        when(projectRepository.findById(1)).thenReturn(Optional.of(project));

        assertThat(writer.synchronize(entry)).isEqualTo(MeetingSynchronizationOutcome.CREATED);

        ArgumentCaptor<Meeting> meetingCaptor = ArgumentCaptor.forClass(Meeting.class);
        verify(meetingRepository).saveAndFlush(meetingCaptor.capture());
        assertThat(meetingCaptor.getValue().getProject()).isSameAs(project);
        assertThat(meetingCaptor.getValue().getRoomName()).isEqualTo(ROOM_NAME);
    }

    @DisplayName("같은 roomName의 Meeting이 이미 있으면 저장하지 않는다.")
    @Test
    void doesNothingForExistingMeeting() {
        when(meetingRepository.existsByRoomName(ROOM_NAME)).thenReturn(true);

        assertThat(writer.synchronize(entry(1, ROOM_NAME)))
                .isEqualTo(MeetingSynchronizationOutcome.ALREADY_EXISTS);

        verify(projectRepository, never()).findById(1);
        verify(meetingRepository, never()).saveAndFlush(org.mockito.ArgumentMatchers.any());
    }

    @DisplayName("Project가 없으면 Meeting을 저장하지 않는다.")
    @Test
    void doesNothingWhenProjectDoesNotExist() {
        when(meetingRepository.existsByRoomName(ROOM_NAME)).thenReturn(false);
        when(projectRepository.findById(99)).thenReturn(Optional.empty());

        assertThat(writer.synchronize(entry(99, ROOM_NAME)))
                .isEqualTo(MeetingSynchronizationOutcome.PROJECT_NOT_FOUND);

        verify(meetingRepository, never()).saveAndFlush(org.mockito.ArgumentMatchers.any());
    }

    private MeetingRoomRedisEntry entry(int projectId, String roomName) {
        return new MeetingRoomRedisEntry("meeting-room:" + roomName, projectId, roomName);
    }
}
