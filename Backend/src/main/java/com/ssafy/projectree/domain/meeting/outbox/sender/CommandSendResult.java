package com.ssafy.projectree.domain.meeting.outbox.sender;

public record CommandSendResult(
        String messageId
) {
}
