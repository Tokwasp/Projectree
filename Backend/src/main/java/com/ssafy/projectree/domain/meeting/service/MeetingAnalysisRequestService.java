package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisRequestedCommand;
import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.dto.response.MeetingAnalysisRequestResponse;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class MeetingAnalysisRequestService {

    private final MeetingRepository meetingRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    @Transactional
    public MeetingAnalysisRequestResponse requestAnalysis(
            int projectId,
            String roomName,
            int memberId,
            MeetingAnalysisRequest request
    ) {
        validateRequest(projectId, roomName, request);

        Meeting meeting = meetingRepository
                .findByProjectIdAndRoomNameForUpdate(projectId, roomName)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));

        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(MeetingErrorCode.MEETING_ACCESS_DENIED);
        }
        if (meeting.isAnalysisRequestConfirmed()) {
            throw new CustomException(MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED);
        }

        boolean generateSummary = request.generateSummary();
        boolean generateNodes = request.generateNodes();
        meeting.confirmAnalysisOptions(generateSummary, generateNodes);

        UUID commandId = UUID.randomUUID();
        MeetingAnalysisCommandType commandType =
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED;
        MeetingAnalysisRequestedCommand command = new MeetingAnalysisRequestedCommand(
                MeetingAnalysisRequestedCommand.CURRENT_SCHEMA_VERSION,
                commandId,
                commandType,
                Instant.now(),
                projectId,
                new MeetingAnalysisRequestedCommand.Payload(
                        meeting.getId(),
                        meeting.getRoomName(),
                        generateSummary,
                        generateNodes
                )
        );

        String payload = serialize(command);
        outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        commandId,
                        meeting,
                        commandType,
                        payload
                )
        );

        return MeetingAnalysisRequestResponse.of(meeting, commandId);
    }

    private void validateRequest(
            int projectId,
            String roomName,
            MeetingAnalysisRequest request
    ) {
        if (projectId <= 0
                || request == null
                || request.generateSummary() == null
                || request.generateNodes() == null) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }
        if (!isCanonicalUuid(roomName)) {
            throw new CustomException(MeetingErrorCode.INVALID_ROOM_NAME);
        }
    }

    private boolean isCanonicalUuid(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            UUID parsed = UUID.fromString(value);
            return parsed.toString().equalsIgnoreCase(value);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private String serialize(MeetingAnalysisRequestedCommand command) {
        try {
            return objectMapper.writeValueAsString(command);
        } catch (JacksonException exception) {
            throw new CustomException(MeetingErrorCode.OUTBOX_SERIALIZATION_FAILED);
        }
    }
}
