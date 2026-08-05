package com.ssafy.projectree.domain.meeting.record.exception;

public class MeetingRecordContentCodecException extends RuntimeException {

    public MeetingRecordContentCodecException(String message) {
        super(message);
    }

    public MeetingRecordContentCodecException(String message, Throwable cause) {
        super(message, cause);
    }
}
