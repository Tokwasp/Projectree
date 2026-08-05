package com.ssafy.projectree.domain.meeting.infrastructure.redis;

import io.lettuce.core.RedisCommandExecutionException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class MeetingRoomRedisReader {

    private static final int MAX_ROOM_NAME_LENGTH = 128;
    private static final String CREATOR_FIELD = "creator";
    private static final String ROOM_FIELD = "room";
    private static final StringRedisSerializer STRING_SERIALIZER = new StringRedisSerializer();

    private final StringRedisTemplate redisTemplate;
    private final MeetingSyncProperties properties;

    public List<MeetingRoomRedisEntry> findAll() {
        List<MeetingRoomRedisEntry> entries = redisTemplate.execute(
                (RedisCallback<List<MeetingRoomRedisEntry>>) this::scan
        );
        return entries == null ? List.of() : entries;
    }

    private List<MeetingRoomRedisEntry> scan(RedisConnection connection) {
        ScanOptions options = ScanOptions.scanOptions()
                .match(properties.keyPrefix() + "*")
                .count(properties.scanCount())
                .build();
        List<MeetingRoomRedisEntry> entries = new ArrayList<>();
        int scannedKeys = 0;

        try (Cursor<byte[]> cursor = connection.keyCommands().scan(options)) {
            while (cursor.hasNext()) {
                scannedKeys++;
                byte[] rawKey = cursor.next();
                String sourceKey = STRING_SERIALIZER.deserialize(rawKey);
                Map<byte[], byte[]> rawFields;
                try {
                    rawFields = connection.hashCommands().hGetAll(rawKey);
                } catch (RuntimeException exception) {
                    if (isWrongType(exception)) {
                        log.warn(
                                "[MeetingSync] Invalid Redis type. Expected HASH. key={}",
                                sourceKey
                        );
                        continue;
                    }
                    throw exception;
                }
                if (rawFields == null || rawFields.isEmpty()) {
                    log.debug("[MeetingSync] Redis entry disappeared during scan. key={}", sourceKey);
                    continue;
                }

                parse(sourceKey, deserialize(rawFields)).ifPresent(entries::add);
            }
        }

        log.debug(
                "[MeetingSync] Redis scan completed. scannedKeys={}, validEntries={}",
                scannedKeys,
                entries.size()
        );
        return entries;
    }

    Optional<MeetingRoomRedisEntry> parse(String sourceKey, Map<String, String> fields) {
        Optional<Integer> parsedProjectId = parseKeyProjectId(sourceKey);
        if (parsedProjectId.isEmpty()) {
            return Optional.empty();
        }

        String rawCreatorMemberId = fields.get(CREATOR_FIELD);
        if (rawCreatorMemberId == null || rawCreatorMemberId.isBlank()) {
            log.warn("[MeetingSync] MISSING_CREATOR. key={}", sourceKey);
            return Optional.empty();
        }

        Integer creatorMemberId;
        try {
            creatorMemberId = Integer.valueOf(rawCreatorMemberId);
        } catch (NumberFormatException exception) {
            log.warn("[MeetingSync] INVALID_CREATOR. key={}", sourceKey);
            return Optional.empty();
        }
        if (creatorMemberId <= 0) {
            log.warn("[MeetingSync] INVALID_CREATOR. key={}", sourceKey);
            return Optional.empty();
        }

        String roomName = fields.get(ROOM_FIELD);
        if (roomName == null || roomName.isBlank()) {
            log.warn("[MeetingSync] MISSING_ROOM_NAME. key={}", sourceKey);
            return Optional.empty();
        }
        if (roomName.length() > MAX_ROOM_NAME_LENGTH || !isCanonicalUuid(roomName)) {
            log.warn("[MeetingSync] INVALID_ROOM_NAME. key={}, roomName={}", sourceKey, roomName);
            return Optional.empty();
        }

        return Optional.of(new MeetingRoomRedisEntry(
                sourceKey,
                parsedProjectId.get(),
                creatorMemberId,
                UUID.fromString(roomName).toString()
        ));
    }

    private Optional<Integer> parseKeyProjectId(String sourceKey) {
        if (sourceKey == null || sourceKey.isBlank() || !sourceKey.startsWith(properties.keyPrefix())) {
            log.warn("[MeetingSync] INVALID_REDIS_KEY. key={}", sourceKey);
            return Optional.empty();
        }

        String suffix = sourceKey.substring(properties.keyPrefix().length());
        if (suffix.isBlank() || suffix.contains(":")) {
            log.warn("[MeetingSync] INVALID_REDIS_KEY. key={}", sourceKey);
            return Optional.empty();
        }
        try {
            int projectId = Integer.parseInt(suffix);
            if (projectId <= 0) {
                log.warn("[MeetingSync] INVALID_PROJECT_ID. key={}", sourceKey);
                return Optional.empty();
            }
            return Optional.of(projectId);
        } catch (NumberFormatException exception) {
            log.warn("[MeetingSync] INVALID_PROJECT_ID. key={}", sourceKey);
            return Optional.empty();
        }
    }

    private Map<String, String> deserialize(Map<byte[], byte[]> rawFields) {
        return rawFields.entrySet().stream()
                .collect(java.util.stream.Collectors.toMap(
                        entry -> STRING_SERIALIZER.deserialize(entry.getKey()),
                        entry -> STRING_SERIALIZER.deserialize(entry.getValue())
                ));
    }

    private boolean isCanonicalUuid(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }

        try {
            UUID parsed = UUID.fromString(value);
            return parsed.toString().equalsIgnoreCase(value);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private boolean isWrongType(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof RedisCommandExecutionException) {
                String message = current.getMessage();
                return message != null
                        && message.regionMatches(true, 0, "WRONGTYPE", 0, "WRONGTYPE".length());
            }
            current = current.getCause();
        }
        return false;
    }
}
