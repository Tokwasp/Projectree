package com.ssafy.projectree.domain.project.controller.dto.response.home;

import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import lombok.Builder;
import lombok.Getter;

@Getter
public class MeetingRecordResponse {
    private long id;
    private String name;

    @Builder
    private MeetingRecordResponse(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public static MeetingRecordResponse of(MeetingRecord meetingRecord) {
        return MeetingRecordResponse.builder()
                .id(meetingRecord.getId())
                .name(meetingRecord.getTitle())
                .build();
    }
}
