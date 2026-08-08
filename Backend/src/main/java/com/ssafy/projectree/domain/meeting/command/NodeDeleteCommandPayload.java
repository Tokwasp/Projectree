package com.ssafy.projectree.domain.meeting.command;

import java.util.List;

public record NodeDeleteCommandPayload(
        List<String> nodeIds,
        long expectedGraphVersion,
        int requestedByMemberId
) {
}
