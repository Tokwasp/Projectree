package com.ssafy.projectree.domain.meeting.infrastructure.redis;

import io.lettuce.core.RedisCommandExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisHashCommands;
import org.springframework.data.redis.connection.RedisKeyCommands;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingRoomRedisReaderTest {

    private static final String PREFIX = "meeting:project:";
    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";
    private static final String OTHER_ROOM_NAME = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";
    private static final StringRedisSerializer SERIALIZER = new StringRedisSerializer();

    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private RedisConnection connection;
    @Mock
    private RedisHashCommands hashCommands;
    @Mock
    private RedisKeyCommands keyCommands;
    @Mock
    private Cursor<byte[]> cursor;

    private MeetingRoomRedisReader reader;

    @BeforeEach
    void setUp() {
        reader = new MeetingRoomRedisReader(
                redisTemplate,
                new MeetingSyncProperties(true, 5000, 200, PREFIX)
        );
    }

    @Test
    @SuppressWarnings("unchecked")
    void scansMeetingProjectHashesAndMapsCreatorAndRoom() {
        stubScan();
        when(cursor.hasNext()).thenReturn(true, true, false);
        when(cursor.next()).thenReturn(bytes(PREFIX + "5"), bytes(PREFIX + "6"));
        when(hashCommands.hGetAll(any(byte[].class))).thenReturn(
                rawFields("722", ROOM_NAME),
                rawFields("723", OTHER_ROOM_NAME)
        );

        assertThat(reader.findAll()).containsExactly(
                new MeetingRoomRedisEntry(PREFIX + "5", 5, 722, ROOM_NAME),
                new MeetingRoomRedisEntry(PREFIX + "6", 6, 723, OTHER_ROOM_NAME)
        );

        ArgumentCaptor<ScanOptions> options = ArgumentCaptor.forClass(ScanOptions.class);
        verify(keyCommands).scan(options.capture());
        assertThat(options.getValue().getPattern()).isEqualTo("meeting:project:*");
        assertThat(options.getValue().getCount()).isEqualTo(200);
    }

    @Test
    void parsesProjectIdFromKeySuffix() {
        assertThat(reader.parse(PREFIX + "5", fields("722", ROOM_NAME)))
                .contains(new MeetingRoomRedisEntry(PREFIX + "5", 5, 722, ROOM_NAME));
    }

    @Test
    void rejectsInvalidProjectKeySuffix() {
        assertThat(reader.parse(PREFIX + "abc", fields("722", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "0", fields("722", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "-1", fields("722", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "1:extra", fields("722", ROOM_NAME))).isEmpty();
        assertThat(reader.parse("meeting:room:" + ROOM_NAME, fields("722", ROOM_NAME))).isEmpty();
    }

    @Test
    void rejectsMissingOrInvalidCreator() {
        assertThat(reader.parse(PREFIX + "5", Map.of("room", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "5", fields("abc", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "5", fields("0", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + "5", fields("-1", ROOM_NAME))).isEmpty();
    }

    @Test
    void rejectsMissingOrNonCanonicalRoom() {
        assertThat(reader.parse(PREFIX + "5", Map.of("creator", "722"))).isEmpty();
        assertThat(reader.parse(PREFIX + "5", fields("722", "not-a-uuid"))).isEmpty();
        assertThat(reader.parse(PREFIX + "5", fields("722", "1-1-1-1-1"))).isEmpty();
        assertThat(reader.parse(
                PREFIX + "5",
                fields("722", "550e8400e29b41d4a716446655440000")
        )).isEmpty();
    }

    @Test
    @SuppressWarnings("unchecked")
    void wrongTypeIsSkippedAndRemainingEntriesAreRead() {
        stubScan();
        when(cursor.hasNext()).thenReturn(true, true, false);
        when(cursor.next()).thenReturn(bytes(PREFIX + "5"), bytes(PREFIX + "6"));
        RedisSystemException wrongType = new RedisSystemException(
                "Redis command failed",
                new RedisCommandExecutionException("WRONGTYPE Operation against a key")
        );
        when(hashCommands.hGetAll(any(byte[].class)))
                .thenThrow(wrongType)
                .thenReturn(rawFields("723", OTHER_ROOM_NAME));

        assertThat(reader.findAll()).containsExactly(
                new MeetingRoomRedisEntry(PREFIX + "6", 6, 723, OTHER_ROOM_NAME)
        );

    }

    @Test
    @SuppressWarnings("unchecked")
    void connectionFailureIsRethrown() {
        stubScan();
        when(cursor.hasNext()).thenReturn(true);
        when(cursor.next()).thenReturn(bytes(PREFIX + "7"));
        RedisConnectionFailureException failure =
                new RedisConnectionFailureException("connection reset");
        when(hashCommands.hGetAll(any(byte[].class))).thenThrow(failure);

        assertThatThrownBy(reader::findAll).isSameAs(failure);
    }

    @SuppressWarnings("unchecked")
    private void stubScan() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenAnswer(invocation -> {
            RedisCallback<?> callback = invocation.getArgument(0);
            return callback.doInRedis(connection);
        });
        when(connection.keyCommands()).thenReturn(keyCommands);
        when(keyCommands.scan(any(ScanOptions.class))).thenReturn(cursor);
        when(connection.hashCommands()).thenReturn(hashCommands);
    }

    private Map<String, String> fields(String creator, String room) {
        return Map.of("creator", creator, "room", room);
    }

    private Map<byte[], byte[]> rawFields(String creator, String room) {
        Map<byte[], byte[]> fields = new LinkedHashMap<>();
        fields.put(bytes("creator"), bytes(creator));
        fields.put(bytes("room"), bytes(room));
        return fields;
    }

    private byte[] bytes(String value) {
        return SERIALIZER.serialize(value);
    }
}
