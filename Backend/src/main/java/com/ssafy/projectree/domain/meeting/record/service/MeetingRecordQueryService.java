package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordDetailResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.LocalDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MeetingRecordQueryService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingRepository meetingRepository;
    private final MeetingRecordRepository meetingRecordRepository;
    private final MeetingAnalysisCommandOutboxRepository commandOutboxRepository;
    private final MeetingRecordContentCodec contentCodec;

    public MeetingRecordDetailResponse getRecord(int projectId, int meetingId, int memberId) {
        // 프로젝트 멤버 검증을 회의록 조회보다 먼저 수행한다.
        // 비회원이 meetingId를 바꿔가며 회의록 존재 여부를 확인할 수 없게 한다.
        requireProjectMember(projectId, memberId);

        Meeting meeting = meetingRepository.findByIdWithProject(meetingId)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));
        if (meeting.getProject().getId() != projectId) {
            throw new CustomException(MeetingErrorCode.MEETING_PROJECT_MISMATCH);
        }

        MeetingRecord record = meetingRecordRepository.findByMeetingId(meetingId)
                .orElseThrow(() -> new CustomException(MeetingRecordErrorCode.MEETING_RECORD_NOT_FOUND));
        EstimatedMeetingTime time = estimateTime(meeting, record);

        return new MeetingRecordDetailResponse(
                record.getId(),
                projectId,
                meetingId,
                record.getTitle(),
                time.startedAt().toLocalDate(),
                time.startedAt(),
                time.endedAt(),
                time.durationMinutes(),
                contentCodec.decode(record.getSummaryJson()),
                contentCodec.decode(record.getDecisionsJson()),
                contentCodec.decode(record.getNextTodosJson()),
                contentCodec.decode(record.getIssuesJson()),
                record.getVersion(),
                record.getCreatedAt(),
                record.getUpdatedAt()
        );
    }

    private void requireProjectMember(int projectId, int memberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
    }

    /**
     * 실제 통화 입·퇴장 기록이 없어 기존 데이터로 추정한다.
     * 시작은 Meeting이 Redis에서 동기화된 시각, 종료는 생성자가 분석 옵션을 확정한 시각이다.
     * Outbox 정보를 쓸 수 없으면 회의록 생성 시각으로 대체하며, 조회 자체를 실패시키지는 않는다.
     * Outbox 보존 기간 정책이 생겨도 회의록 조회가 막히지 않아야 하기 때문이다.
     */
    private EstimatedMeetingTime estimateTime(Meeting meeting, MeetingRecord record) {
        LocalDateTime startedAt = meeting.getCreatedAt();
        if (startedAt == null) {
            log.error(
                    "Meeting 감사 시각이 없어 회의 시간을 추정할 수 없다. meetingId={}, meetingRecordId={}",
                    meeting.getId(),
                    record.getId()
            );
            throw new CustomException(CommonErrorCode.INTERNAL_SERVER_ERROR);
        }

        LocalDateTime endedAt = resolveEndedAt(meeting, record, startedAt);
        long durationMinutes = Math.max(0L, Duration.between(startedAt, endedAt).toMinutes());

        return new EstimatedMeetingTime(startedAt, endedAt, durationMinutes);
    }

    private LocalDateTime resolveEndedAt(
            Meeting meeting,
            MeetingRecord record,
            LocalDateTime startedAt
    ) {
        LocalDateTime analysisRequestedAt = analysisRequestedAt(meeting, record, startedAt);
        if (analysisRequestedAt != null) {
            return analysisRequestedAt;
        }

        LocalDateTime recordCreatedAt = record.getCreatedAt();
        if (recordCreatedAt != null && !recordCreatedAt.isBefore(startedAt)) {
            return recordCreatedAt;
        }
        return startedAt;
    }

    /**
     * Outbox의 createdAt은 다음을 모두 만족할 때만 종료 추정값으로 쓴다.
     * 존재 / 분석 요청 Command / 같은 회의 / 감사 시각 존재 / 시작 시각 이후.
     */
    private LocalDateTime analysisRequestedAt(
            Meeting meeting,
            MeetingRecord record,
            LocalDateTime startedAt
    ) {
        MeetingAnalysisCommandOutbox command = commandOutboxRepository
                .findByCommandIdWithMeetingAndProject(record.getCommandId())
                .orElse(null);
        if (command == null) {
            logFallback(meeting, record, "COMMAND_OUTBOX_NOT_FOUND");
            return null;
        }
        if (command.getCommandType() != MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED) {
            logFallback(meeting, record, "COMMAND_TYPE_MISMATCH");
            return null;
        }
        if (command.getMeeting().getId() != meeting.getId()) {
            logFallback(meeting, record, "COMMAND_MEETING_MISMATCH");
            return null;
        }
        if (command.getCreatedAt() == null) {
            logFallback(meeting, record, "COMMAND_CREATED_AT_MISSING");
            return null;
        }
        if (command.getCreatedAt().isBefore(startedAt)) {
            logFallback(meeting, record, "COMMAND_CREATED_AT_BEFORE_MEETING");
            return null;
        }
        return command.getCreatedAt();
    }

    /**
     * commandId 전체값이나 회의록 내용은 로그에 남기지 않는다.
     */
    private void logFallback(Meeting meeting, MeetingRecord record, String reason) {
        log.warn(
                "회의 종료 시각을 회의록 생성 시각으로 대체한다. meetingId={}, meetingRecordId={}, reason={}",
                meeting.getId(),
                record.getId(),
                reason
        );
    }

    private record EstimatedMeetingTime(
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            long durationMinutes
    ) {
    }
}
