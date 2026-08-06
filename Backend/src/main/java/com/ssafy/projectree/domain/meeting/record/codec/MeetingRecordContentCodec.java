package com.ssafy.projectree.domain.meeting.record.codec;

import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordContentCodecException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;

/**
 * API의 List&lt;String&gt;과 DB의 JSON 배열 문자열을 상호 변환한다.
 * 문자열 배열만 유효한 표현으로 인정하며, 타입 강제 변환에 기대지 않고 트리를 직접 검사한다.
 * 공유 ObjectMapper의 전역 설정은 변경하지 않는다.
 */
@Component
@RequiredArgsConstructor
public class MeetingRecordContentCodec {

    private final ObjectMapper objectMapper;

    public String encode(List<String> items) {
        if (items == null) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 직렬화에 실패했습니다: 항목 목록이 null입니다."
            );
        }
        for (String item : items) {
            if (item == null) {
                throw new MeetingRecordContentCodecException(
                        "회의록 본문 직렬화에 실패했습니다: null 항목은 허용되지 않습니다."
                );
            }
        }

        try {
            return objectMapper.writeValueAsString(items);
        } catch (JacksonException exception) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 직렬화에 실패했습니다.", exception
            );
        }
    }

    /**
     * 아직 본문이 채워지지 않은 컬럼은 NULL이므로 빈 목록으로 취급한다.
     */
    public List<String> decode(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }

        JsonNode root = readTree(json);
        if (root == null || !root.isArray()) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 역직렬화에 실패했습니다: JSON 배열이 아닙니다."
            );
        }

        List<String> items = new ArrayList<>(root.size());
        for (JsonNode element : root) {
            items.add(requireTextElement(element));
        }
        return List.copyOf(items);
    }

    private JsonNode readTree(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (JacksonException exception) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 역직렬화에 실패했습니다: JSON 형식이 올바르지 않습니다.", exception
            );
        }
    }

    private String requireTextElement(JsonNode element) {
        if (element == null || element.isNull()) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 역직렬화에 실패했습니다: null 항목은 허용되지 않습니다."
            );
        }
        if (!element.isString()) {
            throw new MeetingRecordContentCodecException(
                    "회의록 본문 역직렬화에 실패했습니다: 문자열이 아닌 항목이 포함되어 있습니다."
            );
        }
        return element.stringValue();
    }
}
