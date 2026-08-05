package com.ssafy.projectree.domain.meeting.record.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.UUID;

/**
 * Python이 요약 생성 성공 후 호출하는 회의록 최초 생성 Callback 본문.
 * 네 배열은 null을 허용하지 않으며 비어 있으면 빈 배열로 전달한다.
 * JSON 문자열 변환은 이 DTO가 아니라 Service가 MeetingRecordContentCodec으로 수행한다.
 */
public record MeetingRecordCallbackRequest(

        @NotNull
        Integer callbackSchemaVersion,

        @NotNull
        UUID commandId,

        @NotBlank
        @Size(max = 200)
        String title,

        @NotNull
        List<@NotBlank String> summary,

        @NotNull
        List<@NotBlank String> decisions,

        @NotNull
        List<@NotBlank String> nextTodos,

        @NotNull
        List<@NotBlank String> issues
) {
}
