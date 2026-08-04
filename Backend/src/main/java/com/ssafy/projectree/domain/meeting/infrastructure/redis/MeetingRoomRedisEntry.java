package com.ssafy.projectree.domain.meeting.infrastructure.redis;

public record MeetingRoomRedisEntry(
        String sourceKey,
        Integer projectId,
        Integer creatorMemberId,
        String roomName
) {
}
