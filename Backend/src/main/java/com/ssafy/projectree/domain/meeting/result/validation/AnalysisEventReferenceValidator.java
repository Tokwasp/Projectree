package com.ssafy.projectree.domain.meeting.result.validation;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
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
        MeetingAnalysisCommandOutbox command = commandOutboxRepository
                .findByCommandId(event.commandId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result command does not exist"));

        if (command.getCommandType() == null) {
            throw new AnalysisResultContractException("Analysis result command type is not supported");
        }
        switch (command.getCommandType()) {
            case MEETING_ANALYSIS_REQUESTED -> validateMeetingAnalysis(event, command);
            case NODE_CONTENT_UPDATE_REQUESTED -> validateNodeContentUpdate(event, command);
            case NODE_DELETE_REQUESTED -> validateNodeDelete(event, command);
        }
    }

    private void validateMeetingAnalysis(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox command
    ) {
        if (event.meetingId() == null) {
            throw new AnalysisResultContractException("Analysis result meetingId must be positive");
        }
        Meeting meeting = meetingRepository.findByIdWithProject(event.meetingId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result meeting does not exist"));
        if (meeting.getProject().getId() != event.projectId()) {
            throw new AnalysisResultContractException("Analysis result meeting project does not match");
        }

        if (command.getMeeting() == null) {
            throw new AnalysisResultContractException("Analysis result command meeting does not exist");
        }
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

    private void validateNodeContentUpdate(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox command
    ) {
        if (event.eventType() != AnalysisResultEventType.PROJECT_GRAPH_CHANGED
                && event.eventType()
                != AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED) {
            throw new AnalysisResultContractException(
                    "Node content update command does not support result eventType: "
                            + event.eventType()
            );
        }
        if (event.projectId() == null || event.projectId() <= 0) {
            throw new AnalysisResultContractException("Node content update projectId must be positive");
        }
        if (event.meetingId() != null) {
            throw new AnalysisResultContractException("Node content update meetingId must be null");
        }
        if (command.getMeeting() != null) {
            throw new AnalysisResultContractException("Node content update command meeting must be null");
        }
        if (command.getTargetProjectId() == null
                || !command.getTargetProjectId().equals(event.projectId())) {
            throw new AnalysisResultContractException("Node content update command project does not match");
        }
    }

    private void validateNodeDelete(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox command
    ) {
        if (event.eventType() != AnalysisResultEventType.PROJECT_GRAPH_CHANGED
                && event.eventType() != AnalysisResultEventType.NODE_DELETE_REJECTED) {
            throw new AnalysisResultContractException(
                    "Node delete command does not support result eventType: " + event.eventType()
            );
        }
        if (event.meetingId() != null) {
            throw new AnalysisResultContractException("Node delete result meetingId must be null");
        }
        if (command.getMeeting() != null) {
            throw new AnalysisResultContractException("Node delete command meeting must be null");
        }
        if (command.getTargetProjectId() == null
                || !command.getTargetProjectId().equals(event.projectId())) {
            throw new AnalysisResultContractException(
                    "Node delete result projectId does not match command"
            );
        }
    }
}
