package com.ssafy.projectree.domain.meeting.record.dto.response;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;

import java.util.UUID;

/**
 * duplicated는 이번 요청이 회의록을 새로 만들었는지(false) 이미 있던 회의록을 그대로 반환했는지(true)를 나타낸다.
 * 두 경우 모두 HTTP 200이므로 Python은 재시도 성공을 단일 코드로 처리할 수 있다.
 */
public record MeetingRecordCallbackResponse(
        long meetingRecordId,
        int meetingId,
        UUID commandId,
        long version,
        boolean duplicated
) {

    public static MeetingRecordCallbackResponse of(
            MeetingRecord meetingRecord,
            int meetingId,
            boolean duplicated
    ) {
        return new MeetingRecordCallbackResponse(
                meetingRecord.getId(),
                meetingId,
                UUID.fromString(meetingRecord.getCommandId()),
                meetingRecord.getVersion(),
                duplicated
        );
    }
}
