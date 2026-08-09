package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingRecordContentEncoderTest {

    private final MeetingRecordContentCodec codec =
            new MeetingRecordContentCodec(JsonMapper.builder().build());
    private final MeetingRecordContentEncoder encoder =
            new MeetingRecordContentEncoder(codec);

    @DisplayName("네 본문 영역을 JSON 배열로 인코딩하며 순서와 한국어를 보존한다.")
    @Test
    void encodesAllContent() {
        List<String> summary = new ArrayList<>(List.of("첫 요약", "둘째 요약"));

        MeetingRecordContentEncoder.EncodedContent encoded = encoder.encode(
                summary,
                List.of("결정"),
                List.of(),
                List.of("이슈")
        );

        assertThat(codec.decode(encoded.summary())).containsExactly("첫 요약", "둘째 요약");
        assertThat(codec.decode(encoded.decisions())).containsExactly("결정");
        assertThat(encoded.nextTodos()).isEqualTo("[]");
        assertThat(codec.decode(encoded.issues())).containsExactly("이슈");
        assertThat(summary).containsExactly("첫 요약", "둘째 요약");
    }

    @DisplayName("어느 본문 영역이든 TEXT 바이트 한도를 넘으면 동일한 오류를 반환한다.")
    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3})
    void rejectsOversizedContent(int oversizedIndex) {
        List<String> oversized = List.of("가".repeat(22_000));
        List<String> normal = List.of("정상");
        List<List<String>> fields = new ArrayList<>(
                List.of(normal, normal, normal, normal)
        );
        fields.set(oversizedIndex, oversized);

        assertThat(codec.encode(oversized).getBytes(StandardCharsets.UTF_8).length)
                .isGreaterThan(MeetingRecordContentEncoder.MAX_TEXT_BYTES);
        assertThatThrownBy(() -> encoder.encode(
                fields.get(0), fields.get(1), fields.get(2), fields.get(3)
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(MeetingRecordErrorCode.MEETING_RECORD_CONTENT_TOO_LARGE);
    }

    @DisplayName("UTF-8 기준 TEXT 한도 이하의 한국어 본문은 허용한다.")
    @Test
    void acceptsContentWithinLimit() {
        List<String> nearLimit = List.of("가".repeat(21_000));

        MeetingRecordContentEncoder.EncodedContent encoded = encoder.encode(
                nearLimit, List.of(), List.of(), List.of()
        );

        assertThat(encoded.summary().getBytes(StandardCharsets.UTF_8).length)
                .isLessThanOrEqualTo(MeetingRecordContentEncoder.MAX_TEXT_BYTES);
        assertThat(codec.decode(encoded.summary())).isEqualTo(nearLimit);
    }
}
