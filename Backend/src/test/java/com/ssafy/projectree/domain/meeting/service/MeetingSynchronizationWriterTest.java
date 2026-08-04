package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingSynchronizationWriterTest {

    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";
    private static final int PROJECT_ID = 5;
    private static final int CREATOR_MEMBER_ID = 722;

    @Mock
    private MeetingRepository meetingRepository;
    @Mock
    private ProjectRepository projectRepository;
    @Mock
    private ProjectMemberRepository projectMemberRepository;

    private MeetingSynchronizationWriter writer;

    @BeforeEach
    void setUp() {
        writer = new MeetingSynchronizationWriter(
                meetingRepository,
                projectRepository,
                projectMemberRepository
        );
    }

    @Test
    void createsMeetingWithCreatorProjectMember() {
        Fixture fixture = fixture(PROJECT_ID, CREATOR_MEMBER_ID);
        stubProjectAndCreator(fixture);

        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.CREATED);

        ArgumentCaptor<Meeting> meeting = ArgumentCaptor.forClass(Meeting.class);
        verify(meetingRepository).saveAndFlush(meeting.capture());
        assertThat(meeting.getValue().getProject()).isSameAs(fixture.project());
        assertThat(meeting.getValue().getCreatorMemberId())
                .isEqualTo(fixture.creator().getMemberId());
    }

    @Test
    void missingProjectOrCreatorDoesNotCreateMeeting() {
        when(projectRepository.findById(PROJECT_ID)).thenReturn(Optional.empty());
        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.PROJECT_NOT_FOUND);

        Fixture fixture = fixture(PROJECT_ID, CREATOR_MEMBER_ID);
        when(projectRepository.findById(PROJECT_ID)).thenReturn(Optional.of(fixture.project()));
        when(projectMemberRepository.findByProjectIdAndMemberId(
                PROJECT_ID, CREATOR_MEMBER_ID
        )).thenReturn(Optional.empty());
        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.CREATOR_PROJECT_MEMBER_NOT_FOUND);
        verify(meetingRepository, never()).saveAndFlush(
                org.mockito.ArgumentMatchers.any()
        );
    }

    @Test
    void existingMeetingRegistersMissingCreatorAndSameCreatorIsNoOp() {
        Fixture fixture = fixture(PROJECT_ID, CREATOR_MEMBER_ID);
        stubProjectAndCreator(fixture);
        Meeting existing = Meeting.create(fixture.project(), fixture.creator(), ROOM_NAME);
        ReflectionTestUtils.setField(existing, "creatorMemberId", null);
        when(meetingRepository.findByRoomNameForUpdate(ROOM_NAME))
                .thenReturn(Optional.of(existing));

        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.CREATOR_REGISTERED);
        assertThat(existing.getCreatorMemberId()).isEqualTo(fixture.creator().getMemberId());
        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.ALREADY_EXISTS);
    }

    @Test
    void conflictingCreatorIsNotOverwritten() {
        Fixture fixture = fixture(PROJECT_ID, CREATOR_MEMBER_ID);
        ProjectMember other = ProjectMember.createMember(999, ProjectRole.MEMBER);
        fixture.project().addMember(other);
        Meeting existing = Meeting.create(fixture.project(), other, ROOM_NAME);
        when(meetingRepository.findByRoomNameForUpdate(ROOM_NAME))
                .thenReturn(Optional.of(existing));

        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.CREATOR_CONFLICT);
        assertThat(existing.getCreatorMemberId()).isEqualTo(other.getMemberId());
        verify(projectRepository, never()).findById(PROJECT_ID);
        verify(projectMemberRepository, never())
                .findByProjectIdAndMemberId(PROJECT_ID, CREATOR_MEMBER_ID);
    }

    @Test
    void existingMeetingWithSameDepartedCreatorIsNoOpWithoutMembershipLookup() {
        Fixture fixture = fixture(PROJECT_ID, CREATOR_MEMBER_ID);
        Meeting existing = Meeting.create(fixture.project(), fixture.creator(), ROOM_NAME);
        when(meetingRepository.findByRoomNameForUpdate(ROOM_NAME))
                .thenReturn(Optional.of(existing));

        assertThat(writer.synchronize(entry()))
                .isEqualTo(MeetingSynchronizationOutcome.ALREADY_EXISTS);

        verify(projectRepository, never()).findById(PROJECT_ID);
        verify(projectMemberRepository, never())
                .findByProjectIdAndMemberId(PROJECT_ID, CREATOR_MEMBER_ID);
    }

    private void stubProjectAndCreator(Fixture fixture) {
        when(projectRepository.findById(PROJECT_ID))
                .thenReturn(Optional.of(fixture.project()));
        when(projectMemberRepository.findByProjectIdAndMemberId(
                PROJECT_ID, CREATOR_MEMBER_ID
        )).thenReturn(Optional.of(fixture.creator()));
    }

    private MeetingRoomRedisEntry entry() {
        return new MeetingRoomRedisEntry(
                "meeting:project:" + PROJECT_ID,
                PROJECT_ID,
                CREATOR_MEMBER_ID,
                ROOM_NAME
        );
    }

    private Fixture fixture(int projectId, int creatorMemberId) {
        Project project = Project.builder().title("project").content("content").build();
        ReflectionTestUtils.setField(project, "id", projectId);
        ProjectMember creator = ProjectMember.createMember(
                creatorMemberId, ProjectRole.OWNER
        );
        project.addMember(creator);
        ReflectionTestUtils.setField(creator, "id", 71);
        return new Fixture(project, creator);
    }

    private record Fixture(Project project, ProjectMember creator) {
    }
}
