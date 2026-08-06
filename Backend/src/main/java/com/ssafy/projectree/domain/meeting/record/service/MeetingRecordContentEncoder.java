package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class MeetingRecordContentEncoder {

    static final int MAX_TEXT_BYTES = 65_535;

    private final MeetingRecordContentCodec contentCodec;

    public EncodedContent encode(
            List<String> summary,
            List<String> decisions,
            List<String> nextTodos,
            List<String> issues
    ) {
        return new EncodedContent(
                encodeAndValidateText(summary),
                encodeAndValidateText(decisions),
                encodeAndValidateText(nextTodos),
                encodeAndValidateText(issues)
        );
    }

    private String encodeAndValidateText(List<String> items) {
        String json = contentCodec.encode(items);
        int byteLength = json.getBytes(StandardCharsets.UTF_8).length;
        if (byteLength > MAX_TEXT_BYTES) {
            log.warn("회의록 본문이 TEXT 한도를 초과했다. byteLength={}", byteLength);
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_CONTENT_TOO_LARGE);
        }
        return json;
    }

    public record EncodedContent(
            String summary,
            String decisions,
            String nextTodos,
            String issues
    ) {
    }
}
