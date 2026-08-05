package com.ssafy.projectree.domain.meeting.outbox.sender;

public interface MeetingAnalysisCommandSender {
    void send(String commandId, String payload);
}
