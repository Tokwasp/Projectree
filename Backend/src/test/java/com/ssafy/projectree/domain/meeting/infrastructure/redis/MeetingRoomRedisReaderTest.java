package com.ssafy.projectree.domain.meeting.infrastructure.redis;

import io.lettuce.core.RedisCommandExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisHashCommands;
import org.springframework.data.redis.connection.RedisKeyCommands;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingRoomRedisReaderTest {

    private static final String PREFIX = "meeting-room:";
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

    @DisplayName("SCAN cursor의 모든 결과를 순회하고 유효한 HASH만 반환한다.")
    @Test
    @SuppressWarnings("unchecked")
    void scansAllCursorResultsAndSkipsDisappearedKey() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenAnswer(invocation -> {
            RedisCallback<?> callback = invocation.getArgument(0);
            return callback.doInRedis(connection);
        });
        when(connection.keyCommands()).thenReturn(keyCommands);
        when(keyCommands.scan(any(org.springframework.data.redis.core.ScanOptions.class)))
                .thenReturn(cursor);
        when(connection.hashCommands()).thenReturn(hashCommands);
        when(cursor.hasNext()).thenReturn(true, true, true, false);
        when(cursor.next()).thenReturn(
                bytes(PREFIX + ROOM_NAME),
                bytes(PREFIX + OTHER_ROOM_NAME),
                bytes(PREFIX + "deadbeef-dead-beef-dead-beefdeadbeef")
        );
        when(hashCommands.hGetAll(any(byte[].class))).thenReturn(
                rawFields("1", ROOM_NAME),
                rawFields("2", OTHER_ROOM_NAME),
                Map.of()
        );

        assertThat(reader.findAll())
                .containsExactly(
                        new MeetingRoomRedisEntry(PREFIX + ROOM_NAME, 1, ROOM_NAME),
                        new MeetingRoomRedisEntry(PREFIX + OTHER_ROOM_NAME, 2, OTHER_ROOM_NAME)
                );

        ArgumentCaptor<ScanOptions> optionsCaptor = ArgumentCaptor.forClass(ScanOptions.class);
        verify(keyCommands).scan(optionsCaptor.capture());
        assertThat(optionsCaptor.getValue().getPattern()).isEqualTo(PREFIX + "*");
        assertThat(optionsCaptor.getValue().getCount()).isEqualTo(200);
    }

    @DisplayName("UUID가 아닌 roomName은 건너뛴다.")
    @Test
    void rejectsNonUuidRoomName() {
        Optional<MeetingRoomRedisEntry> result = reader.parse(
                PREFIX + "not-a-uuid",
                fields("1", "not-a-uuid")
        );

        assertThat(result).isEmpty();
    }

    @DisplayName("UUID.fromString이 허용하는 축약 UUID도 canonical 형식이 아니면 거절한다.")
    @Test
    void rejectsAbbreviatedUuid() {
        assertThat(reader.parse(PREFIX + "1-1-1-1-1", fields("1", "1-1-1-1-1"))).isEmpty();
    }

    @DisplayName("하이픈이 없는 UUID는 거절한다.")
    @Test
    void rejectsUuidWithoutHyphens() {
        String withoutHyphens = "550e8400e29b41d4a716446655440000";

        assertThat(reader.parse(
                PREFIX + withoutHyphens,
                fields("1", withoutHyphens)
        )).isEmpty();
    }

    @DisplayName("Key는 canonical UUID여도 HASH roomName이 축약 UUID이면 거절한다.")
    @Test
    void rejectsAbbreviatedValueRoomName() {
        assertThat(reader.parse(PREFIX + ROOM_NAME, fields("1", "1-1-1-1-1"))).isEmpty();
    }

    @DisplayName("Key와 HASH의 roomName이 다르면 건너뛴다.")
    @Test
    void rejectsRoomNameMismatch() {
        Optional<MeetingRoomRedisEntry> result = reader.parse(
                PREFIX + ROOM_NAME,
                fields("1", OTHER_ROOM_NAME)
        );

        assertThat(result).isEmpty();
    }

    @DisplayName("projectId가 누락되거나 숫자가 아니거나 양수가 아니면 건너뛴다.")
    @Test
    void rejectsInvalidProjectId() {
        assertThat(reader.parse(PREFIX + ROOM_NAME, Map.of("roomName", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + ROOM_NAME, fields("abc", ROOM_NAME))).isEmpty();
        assertThat(reader.parse(PREFIX + ROOM_NAME, fields("0", ROOM_NAME))).isEmpty();
    }

    @DisplayName("roomName 필드가 누락되면 건너뛴다.")
    @Test
    void rejectsMissingRoomName() {
        assertThat(reader.parse(PREFIX + ROOM_NAME, Map.of("projectId", "1"))).isEmpty();
    }

    @DisplayName("설정된 prefix 밖의 Key는 건너뛴다.")
    @Test
    void rejectsKeyOutsidePrefix() {
        assertThat(reader.parse("other:" + ROOM_NAME, fields("1", ROOM_NAME))).isEmpty();
    }

    @DisplayName("정상 HASH를 MeetingRoomRedisEntry로 변환한다.")
    @Test
    void parsesValidHash() {
        assertThat(reader.parse(PREFIX + ROOM_NAME, fields("15", ROOM_NAME)))
                .contains(new MeetingRoomRedisEntry(PREFIX + ROOM_NAME, 15, ROOM_NAME));
    }

    @DisplayName("WRONGTYPE Key는 건너뛰고 다음 정상 HASH를 계속 읽는다.")
    @Test
    @SuppressWarnings("unchecked")
    void skipsWrongTypeAndContinuesReading() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenAnswer(invocation -> {
            RedisCallback<?> callback = invocation.getArgument(0);
            return callback.doInRedis(connection);
        });
        when(connection.keyCommands()).thenReturn(keyCommands);
        when(keyCommands.scan(any(ScanOptions.class))).thenReturn(cursor);
        when(connection.hashCommands()).thenReturn(hashCommands);
        when(cursor.hasNext()).thenReturn(true, true, false);
        when(cursor.next()).thenReturn(
                bytes(PREFIX + OTHER_ROOM_NAME),
                bytes(PREFIX + ROOM_NAME)
        );
        RedisSystemException wrongType = new RedisSystemException(
                "Redis command failed",
                new RedisCommandExecutionException(
                        "WRONGTYPE Operation against a key holding the wrong kind of value"
                )
        );
        when(hashCommands.hGetAll(any(byte[].class)))
                .thenThrow(wrongType)
                .thenReturn(rawFields("1", ROOM_NAME));

        assertThat(reader.findAll())
                .containsExactly(new MeetingRoomRedisEntry(PREFIX + ROOM_NAME, 1, ROOM_NAME));
    }

    @DisplayName("Redis 연결 장애는 WRONGTYPE으로 삼키지 않고 재전파한다.")
    @Test
    @SuppressWarnings("unchecked")
    void rethrowsConnectionFailure() {
        when(redisTemplate.execute(any(RedisCallback.class))).thenAnswer(invocation -> {
            RedisCallback<?> callback = invocation.getArgument(0);
            return callback.doInRedis(connection);
        });
        when(connection.keyCommands()).thenReturn(keyCommands);
        when(keyCommands.scan(any(ScanOptions.class))).thenReturn(cursor);
        when(connection.hashCommands()).thenReturn(hashCommands);
        when(cursor.hasNext()).thenReturn(true);
        when(cursor.next()).thenReturn(bytes(PREFIX + ROOM_NAME));
        RedisConnectionFailureException connectionFailure =
                new RedisConnectionFailureException("connection reset");
        when(hashCommands.hGetAll(any(byte[].class))).thenThrow(connectionFailure);

        assertThatThrownBy(reader::findAll).isSameAs(connectionFailure);
    }

    private Map<String, String> fields(String projectId, String roomName) {
        return Map.of("projectId", projectId, "roomName", roomName);
    }

    private Map<byte[], byte[]> rawFields(String projectId, String roomName) {
        Map<byte[], byte[]> fields = new LinkedHashMap<>();
        fields.put(bytes("projectId"), bytes(projectId));
        fields.put(bytes("roomName"), bytes(roomName));
        return fields;
    }

    private byte[] bytes(String value) {
        return SERIALIZER.serialize(value);
    }
}
