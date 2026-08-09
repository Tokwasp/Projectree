package com.ssafy.projectree.domain.meeting.outbox.sender;

public interface MeetingAnalysisCommandSender {
    CommandSendResult send(String commandId, String payload);
}
