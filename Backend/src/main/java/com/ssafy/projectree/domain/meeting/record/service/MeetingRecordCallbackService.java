package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordCallbackRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordCallbackResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.event.MeetingRecordCreatedNotificationEvent;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;


/**
 * Python이 생성한 회의록 초안을 최초 1회 저장한다.
 * 같은 commandId로 재시도가 들어와도 기존 회의록을 절대 수정하지 않는다.
 * 사용자가 회의록을 수정한 뒤 Python이 재시도하는 상황에서 사용자 편집이 사라지지 않게 하기 위한 정책이다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MeetingRecordCallbackService {

    static final int SUPPORTED_CALLBACK_SCHEMA_VERSION = 1;

    private final MeetingRepository meetingRepository;
    private final MeetingAnalysisCommandOutboxRepository commandOutboxRepository;
    private final MeetingRecordRepository meetingRecordRepository;
    private final MeetingRecordContentEncoder contentEncoder;
    private final ApplicationEventPublisher applicationEventPublisher;

    @Transactional
    public MeetingRecordCallbackResponse receive(
            int meetingId,
            MeetingRecordCallbackRequest request
    ) {
        validateSchemaVersion(request.callbackSchemaVersion());
        String commandId = request.commandId().toString();
        log.info(
                "[AnalysisFlow] RECORD_CALLBACK_RECEIVED. commandId={}, meetingId={}, callbackSchemaVersion={}",
                commandId,
                meetingId,
                request.callbackSchemaVersion()
        );

        // 같은 Meeting에 대한 동시 Callback을 직렬화한다.
        // 두 요청이 동시에 "회의록 없음"으로 판단하는 race를 막는 것이 목적이다.
        Meeting meeting = meetingRepository.findByIdForUpdate(meetingId)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));
        MeetingAnalysisCommandOutbox command = validateCommand(commandId, meeting);

        MeetingRecord existing = meetingRecordRepository.findByMeetingId(meetingId).orElse(null);
        if (existing != null) {
            return duplicated(existing, meetingId, commandId);
        }
        validateCommandNotUsedByAnotherRecord(commandId, meetingId);

        // 저장 부수 효과가 생기기 전에 본문 인코딩과 크기 검증을 끝낸다.
        MeetingRecordContentEncoder.EncodedContent content = contentEncoder.encode(
                request.summary(),
                request.decisions(),
                request.nextTodos(),
                request.issues()
        );
        completeSummaryAnalysis(meeting);

        MeetingRecord created = meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting,
                request.commandId(),
                request.title(),
                content.summary(),
                content.decisions(),
                content.nextTodos(),
                content.issues()
        ));
        applicationEventPublisher.publishEvent(
                new MeetingRecordCreatedNotificationEvent(
                        command.getRequestedByMemberId()
                )
        );
        log.info(
                "[AnalysisFlow] RECORD_CALLBACK_SAVED. commandId={}, meetingId={}, meetingRecordId={}, requestedByMemberId={}",
                commandId,
                meetingId,
                created.getId(),
                command.getRequestedByMemberId()
        );

        return MeetingRecordCallbackResponse.of(created, meetingId, false);
    }

    private void validateSchemaVersion(int callbackSchemaVersion) {
        if (callbackSchemaVersion != SUPPORTED_CALLBACK_SCHEMA_VERSION) {
            throw new CustomException(
                    MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_SCHEMA_UNSUPPORTED
            );
        }
    }

    /**
     * Callback의 commandId는 Java가 Command SQS로 발행한 분석 요청이어야 한다.
     * Outbox 행은 발행 후에도 보존되므로 Callback 도착 시점에 조회할 수 있다.
     */
    private MeetingAnalysisCommandOutbox validateCommand(String commandId, Meeting meeting) {
        MeetingAnalysisCommandOutbox command = commandOutboxRepository
                .findByCommandIdWithMeetingAndProject(commandId)
                .orElseThrow(() -> new CustomException(
                        MeetingRecordErrorCode.MEETING_RECORD_COMMAND_NOT_FOUND
                ));
        if (command.getMeeting().getId() != meeting.getId()) {
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_COMMAND_MISMATCH);
        }
        if (command.getCommandType() != MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED) {
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_COMMAND_MISMATCH);
        }
        if (!meeting.isGenerateSummary()) {
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_NOT_REQUESTED);
        }
        return command;
    }

    /**
     * command_id UNIQUE 위반이 500으로 새지 않도록 저장 전에 확인한다.
     * commandId와 meetingId 일치를 이미 검증했으므로 정상 흐름에서는 도달하지 않는다.
     */
    private void validateCommandNotUsedByAnotherRecord(String commandId, int meetingId) {
        meetingRecordRepository.findByCommandId(commandId).ifPresent(other -> {
            log.warn(
                    "commandId가 다른 회의의 회의록에 이미 사용되었다. meetingId={}, otherRecordId={}",
                    meetingId,
                    other.getId()
            );
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_COMMAND_MISMATCH);
        });
    }

    /**
     * 재시도는 기존 회의록을 그대로 반환한다. update를 호출하지 않으므로 version도 증가하지 않는다.
     */
    private MeetingRecordCallbackResponse duplicated(
            MeetingRecord existing,
            int meetingId,
            String commandId
    ) {
        if (!existing.getCommandId().equals(commandId)) {
            throw new CustomException(
                    MeetingRecordErrorCode.MEETING_RECORD_ALREADY_CREATED_BY_ANOTHER_COMMAND
            );
        }

        log.info(
                "[AnalysisFlow] RECORD_CALLBACK_DUPLICATE. commandId={}, meetingId={}, meetingRecordId={}",
                commandId,
                meetingId,
                existing.getId()
        );
        return MeetingRecordCallbackResponse.of(existing, meetingId, true);
    }

    /**
     * 상태 전이는 Meeting 도메인 메서드를 그대로 사용한다.
     * 실패로 확정된 분석에 성공 Callback을 받으면 회의록만 남고 상태는 FAILED인 모순이 생기므로,
     * ALREADY_FAILED는 저장 전에 409로 차단한다.
     * ALREADY_SUCCEEDED는 허용한다. 기존 MEETING_SUMMARY_READY SQS 이벤트가 Callback보다 먼저
     * 도착해 상태만 SUCCEEDED로 바꿔 둔 경우에도 실제 회의록 데이터는 저장해야 한다.
     */
    private void completeSummaryAnalysis(Meeting meeting) {
        AnalysisTaskCompletionResult result;
        try {
            result = meeting.completeSummaryAnalysis();
        } catch (IllegalStateException exception) {
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_NOT_REQUESTED);
        }

        if (result == AnalysisTaskCompletionResult.ALREADY_FAILED) {
            log.warn(
                    "실패로 확정된 요약 분석에 성공 Callback이 도착해 저장을 거부한다. meetingId={}",
                    meeting.getId()
            );
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_ALREADY_FAILED);
        }
    }

}
