package com.ssafy.projectree.domain.project.controller.dto.response.home;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import lombok.Builder;
import lombok.Getter;

@Getter
public class MeetingRecordResponse {
    private int meetingId;
    private String name;

    @Builder
    private MeetingRecordResponse(int meetingId, String name) {
        this.meetingId = meetingId;
        this.name = name;
    }

    public static MeetingRecordResponse of(MeetingRecord meetingRecord) {
        return MeetingRecordResponse.builder()
                .meetingId(meetingRecord.getMeeting().getId())
                .name(meetingRecord.getTitle())
                .build();
    }
}
