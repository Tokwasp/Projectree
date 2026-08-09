package com.ssafy.projectree.domain.meeting.record.dto.response;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 프론트 회의록 상세 응답.
 * startedAt과 endedAt은 실제 WebRTC 입·퇴장 시각이 아니라 기존 데이터로 계산한 추정값이다.
 * 내부 식별자인 commandId는 노출하지 않으며, 실제 참석자를 증명할 데이터가 없어 participants도 없다.
 */
public record MeetingRecordDetailResponse(
        long meetingRecordId,
        int projectId,
        int meetingId,
        String title,
        LocalDate meetingDate,
        LocalDateTime startedAt,
        LocalDateTime endedAt,
        long durationMinutes,
        List<String> summary,
        List<String> decisions,
        List<String> nextTodos,
        List<String> issues,
        long version,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
}
