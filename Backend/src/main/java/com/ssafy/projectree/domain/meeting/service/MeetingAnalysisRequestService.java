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
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.UUID;

@Service
@Slf4j
@RequiredArgsConstructor
public class MeetingAnalysisRequestService {

    private final MeetingRepository meetingRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final ProjectGraphOperationGuard graphOperationGuard;

    @Transactional
    public MeetingAnalysisRequestResponse requestAnalysis(
            int projectId,
            String roomName,
            int memberId,
            MeetingAnalysisRequest request
    ) {
        validateRequest(projectId, request);
        String canonicalRoomName = canonicalizeRoomName(roomName);

        projectRepository.findByIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        Meeting meeting = meetingRepository
                .findByProjectIdAndRoomNameForUpdate(projectId, canonicalRoomName)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));

        ProjectMember requester = projectMemberRepository
                .findByProjectIdAndMemberId(projectId, memberId)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_ACCESS_DENIED));
        if (meeting.getCreatorMemberId() == null) {
            throw new CustomException(MeetingErrorCode.MEETING_CREATOR_NOT_REGISTERED);
        }
        if (!meeting.isCreatedBy(requester)) {
            throw new CustomException(MeetingErrorCode.MEETING_ANALYSIS_CREATOR_ONLY);
        }
        if (meeting.isAnalysisRequestConfirmed()) {
            throw new CustomException(MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED);
        }

        boolean generateSummary = request.generateSummary();
        boolean generateNodes = request.generateNodes();
        UUID commandId = UUID.randomUUID();
        MeetingAnalysisCommandType commandType =
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED;
        Instant requestedAt = Instant.now(clock);
        if (generateNodes) {
            graphOperationGuard.acquire(
                    projectId,
                    commandId,
                    commandType,
                    requestedAt
            );
        }
        meeting.confirmAnalysisOptions(generateSummary, generateNodes);

        MeetingAnalysisRequestedCommand command = new MeetingAnalysisRequestedCommand(
                MeetingAnalysisRequestedCommand.CURRENT_SCHEMA_VERSION,
                commandId,
                commandType,
                requestedAt,
                projectId,
                new MeetingAnalysisRequestedCommand.Payload(
                        meeting.getId(),
                        meeting.getRoomName(),
                        generateSummary,
                        generateNodes
                )
        );

        String payload = serialize(command);
        MeetingAnalysisCommandOutbox outbox = MeetingAnalysisCommandOutbox.pending(
                commandId,
                meeting,
                commandType,
                payload,
                memberId,
                LocalDateTime.now(clock)
        );
        outboxRepository.saveAndFlush(outbox);
        log.info(
                "[AnalysisFlow] ANALYSIS_COMMAND_STAGED. commandId={}, outboxId={}, projectId={}, meetingId={}, requestedByMemberId={}, generateSummary={}, generateNodes={}",
                commandId,
                outbox.getId(),
                projectId,
                meeting.getId(),
                memberId,
                generateSummary,
                generateNodes
        );

        return MeetingAnalysisRequestResponse.of(meeting, commandId);
    }

    private void validateRequest(
            int projectId,
            MeetingAnalysisRequest request
    ) {
        if (projectId <= 0
                || request == null
                || request.generateSummary() == null
                || request.generateNodes() == null) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }
    }

    private String canonicalizeRoomName(String roomName) {
        if (roomName == null || roomName.isBlank()) {
            throw new CustomException(MeetingErrorCode.INVALID_ROOM_NAME);
        }
        try {
            UUID parsed = UUID.fromString(roomName);
            if (!parsed.toString().equalsIgnoreCase(roomName)) {
                throw new CustomException(MeetingErrorCode.INVALID_ROOM_NAME);
            }
            return parsed.toString();
        } catch (IllegalArgumentException exception) {
            throw new CustomException(MeetingErrorCode.INVALID_ROOM_NAME);
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
