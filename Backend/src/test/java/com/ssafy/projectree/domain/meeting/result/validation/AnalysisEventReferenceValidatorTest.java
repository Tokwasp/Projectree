package com.ssafy.projectree.domain.meeting.result.validation;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.project.entity.Project;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

@ExtendWith(MockitoExtension.class)
class AnalysisEventReferenceValidatorTest {

    @Mock
    private MeetingRepository meetingRepository;

    @Mock
    private MeetingAnalysisCommandOutboxRepository commandRepository;

    @InjectMocks
    private AnalysisEventReferenceValidator validator;

    @Test
    void acceptsPendingCommandWhenMeetingAndProjectReferencesMatch() {
        AnalysisResultEventEnvelope event = event(10, 20, 30);
        Meeting meeting = meeting(20, 10);
        MeetingAnalysisCommandOutbox command = command(meeting);
        given(command.getCommandType()).willReturn(MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED);
        given(command.getStatus()).willReturn(MeetingAnalysisOutboxStatus.PENDING);
        given(meetingRepository.findByIdWithProject(20)).willReturn(Optional.of(meeting));
        given(commandRepository.findByCommandId(event.commandId()))
                .willReturn(Optional.of(command));

        assertThatCode(() -> validator.validateReferences(event)).doesNotThrowAnyException();
        org.assertj.core.api.Assertions.assertThat(command.getStatus())
                .isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
    }

    @Test
    void rejectsMissingAndMismatchedReferences() {
        AnalysisResultEventEnvelope event = event(10, 20, 30);
        MeetingAnalysisCommandOutbox command = mock(MeetingAnalysisCommandOutbox.class);
        given(command.getCommandType()).willReturn(MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED);
        given(commandRepository.findByCommandId(event.commandId())).willReturn(Optional.of(command));
        given(meetingRepository.findByIdWithProject(20)).willReturn(Optional.empty());

        assertThatThrownBy(() -> validator.validateReferences(event))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void rejectsMissingCommandAndCommandForAnotherProject() {
        AnalysisResultEventEnvelope event = event(10, 20, 30);
        Meeting meeting = meeting(20, 10);
        given(commandRepository.findByCommandId(event.commandId()))
                .willReturn(Optional.empty());

        assertThatThrownBy(() -> validator.validateReferences(event))
                .isInstanceOf(AnalysisResultContractException.class);

        Meeting commandMeeting = meeting(20, 11);
        MeetingAnalysisCommandOutbox command = command(commandMeeting);
        given(commandRepository.findByCommandId(event.commandId()))
                .willReturn(Optional.of(command));
        given(meetingRepository.findByIdWithProject(20)).willReturn(Optional.of(meeting));

        assertThatThrownBy(() -> validator.validateReferences(event))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void rejectsCommandForAnotherMeetingOrProjectOrType() {
        AnalysisResultEventEnvelope event = event(10, 20, 30);
        Meeting meeting = meeting(20, 10);
        Meeting otherMeeting = mock(Meeting.class);
        given(otherMeeting.getId()).willReturn(21);
        MeetingAnalysisCommandOutbox command = command(otherMeeting);
        given(meetingRepository.findByIdWithProject(20)).willReturn(Optional.of(meeting));
        given(command.getCommandType()).willReturn(MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED);
        given(commandRepository.findByCommandId(event.commandId()))
                .willReturn(Optional.of(command));

        assertThatThrownBy(() -> validator.validateReferences(event))
                .isInstanceOf(AnalysisResultContractException.class);

        MeetingAnalysisCommandOutbox invalidType = mock(MeetingAnalysisCommandOutbox.class);
        given(invalidType.getMeeting()).willReturn(meeting);
        given(invalidType.getCommandType()).willReturn(null);
        given(commandRepository.findByCommandId(event.commandId()))
                .willReturn(Optional.of(invalidType));

        assertThatThrownBy(() -> validator.validateReferences(event))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private Meeting meeting(int meetingId, int projectId) {
        Meeting meeting = mock(Meeting.class);
        Project project = mock(Project.class);
        given(meeting.getId()).willReturn(meetingId);
        given(meeting.getProject()).willReturn(project);
        given(project.getId()).willReturn(projectId);
        return meeting;
    }

    private MeetingAnalysisCommandOutbox command(Meeting meeting) {
        MeetingAnalysisCommandOutbox command = mock(MeetingAnalysisCommandOutbox.class);
        given(command.getMeeting()).willReturn(meeting);
        return command;
    }

    private AnalysisResultEventEnvelope event(int projectId, int meetingId, int ignoredCommandId) {
        return new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(),
                projectId,
                meetingId,
                UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
    }
}
