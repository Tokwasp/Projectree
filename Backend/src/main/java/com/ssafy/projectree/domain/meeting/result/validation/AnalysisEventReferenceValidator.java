package com.ssafy.projectree.domain.meeting.result.validation;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class AnalysisEventReferenceValidator {

    private final MeetingRepository meetingRepository;
    private final MeetingAnalysisCommandOutboxRepository commandOutboxRepository;

    @Transactional(readOnly = true)
    public void validateReferences(AnalysisResultEventEnvelope event) {
        Meeting meeting = meetingRepository.findByIdWithProject(event.meetingId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result meeting does not exist"));
        if (meeting.getProject().getId() != event.projectId()) {
            throw new AnalysisResultContractException("Analysis result meeting project does not match");
        }

        MeetingAnalysisCommandOutbox command = commandOutboxRepository
                .findByCommandIdWithMeetingAndProject(event.commandId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result command does not exist"));
        if (command.getMeeting().getId() != meeting.getId()) {
            throw new AnalysisResultContractException("Analysis result command meeting does not match");
        }
        if (command.getMeeting().getProject().getId() != event.projectId()) {
            throw new AnalysisResultContractException("Analysis result command project does not match");
        }
        if (command.getCommandType() != MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED) {
            throw new AnalysisResultContractException("Analysis result command type is not supported");
        }
    }
}
