package com.ssafy.projectree.domain.meeting.record.codec;

import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordContentCodecException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingRecordContentCodecTest {

    private final ObjectMapper objectMapper = JsonMapper.builder().build();
    private final MeetingRecordContentCodec codec = new MeetingRecordContentCodec(objectMapper);

    @DisplayName("일반 문자열 목록은 round-trip에서 원본과 동일하다.")
    @Test
    void roundTripsPlainStrings() {
        List<String> items = List.of("first", "second", "third");

        String encoded = codec.encode(items);

        assertThat(encoded).isEqualTo("[\"first\",\"second\",\"third\"]");
        assertThat(codec.decode(encoded)).containsExactlyElementsOf(items);
    }

    @DisplayName("빈 목록은 빈 JSON 배열로 저장하고 다시 빈 목록으로 읽는다.")
    @Test
    void encodesEmptyListAsEmptyJsonArray() {
        assertThat(codec.encode(List.of())).isEqualTo("[]");
        assertThat(codec.decode("[]")).isEmpty();
    }

    @DisplayName("한국어를 이스케이프하지 않고 그대로 보존한다.")
    @Test
    void preservesKorean() {
        List<String> items = List.of("첫 번째 요약", "두 번째 요약");

        String encoded = codec.encode(items);

        assertThat(encoded).isEqualTo("[\"첫 번째 요약\",\"두 번째 요약\"]");
        assertThat(codec.decode(encoded)).containsExactlyElementsOf(items);
    }

    @DisplayName("따옴표, 역슬래시, 줄바꿈, 탭을 round-trip에서 보존한다.")
    @Test
    void preservesSpecialCharacters() {
        List<String> items = List.of(
                "그가 \"확정\"이라고 말했다",
                "경로는 C:\\temp\\file 이다",
                "첫 줄\n두 번째 줄",
                "앞\t뒤"
        );

        String encoded = codec.encode(items);

        assertThat(codec.decode(encoded)).containsExactlyElementsOf(items);
    }

    @DisplayName("입력 목록을 변경하지 않는다.")
    @Test
    void doesNotMutateInput() {
        List<String> items = new ArrayList<>(List.of("first", "second"));

        codec.encode(items);

        assertThat(items).containsExactly("first", "second");
    }

    @DisplayName("DB 값이 null이거나 공백이면 빈 목록을 반환한다.")
    @ParameterizedTest
    @ValueSource(strings = {"", " ", "\t", "\n", "   "})
    void decodesBlankAsEmptyList(String json) {
        assertThat(codec.decode(json)).isEmpty();
    }

    @DisplayName("DB 값이 null이면 빈 목록을 반환한다.")
    @Test
    void decodesNullAsEmptyList() {
        assertThat(codec.decode(null)).isEmpty();
    }

    @DisplayName("복호화 결과는 수정할 수 없다.")
    @Test
    void decodeReturnsImmutableList() {
        List<String> decoded = codec.decode("[\"first\"]");

        assertThatThrownBy(() -> decoded.add("second"))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @DisplayName("null 목록은 직렬화할 수 없다.")
    @Test
    void rejectsNullList() {
        assertThatThrownBy(() -> codec.encode(null))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("직렬화");
    }

    @DisplayName("null 요소가 포함된 목록은 직렬화할 수 없다.")
    @Test
    void rejectsNullElementInList() {
        List<String> items = Arrays.asList("정상", null);

        assertThatThrownBy(() -> codec.encode(items))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("직렬화");
    }

    @DisplayName("JSON 형식이 아닌 값은 복호화할 수 없다.")
    @ParameterizedTest
    @ValueSource(strings = {"not-json", "[\"unclosed\"", "[,]", "{\"a\":}"})
    void rejectsMalformedJson(String json) {
        assertThatThrownBy(() -> codec.decode(json))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("역직렬화");
    }

    @DisplayName("JSON 배열이 아닌 값은 복호화할 수 없다.")
    @ParameterizedTest
    @ValueSource(strings = {"{\"text\":\"not-array\"}", "\"plain string\"", "42", "true", "null"})
    void rejectsNonArrayJson(String json) {
        assertThatThrownBy(() -> codec.decode(json))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("JSON 배열이 아닙니다");
    }

    @DisplayName("문자열이 아닌 요소가 포함된 JSON 배열은 복호화할 수 없다.")
    @ParameterizedTest
    @ValueSource(strings = {"[1,2,3]", "[true]", "[[\"nested\"]]", "[{\"a\":\"b\"}]", "[\"정상\",1]"})
    void rejectsNonStringElements(String json) {
        assertThatThrownBy(() -> codec.decode(json))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("문자열이 아닌 항목");
    }

    @DisplayName("null 요소가 포함된 JSON 배열은 복호화할 수 없다.")
    @Test
    void rejectsNullElementInJsonArray() {
        assertThatThrownBy(() -> codec.decode("[\"정상\", null]"))
                .isInstanceOf(MeetingRecordContentCodecException.class)
                .hasMessageContaining("null 항목");
    }
}
