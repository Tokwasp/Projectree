package com.ssafy.projectree.domain.meeting.record.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.util.List;

public record MeetingRecordUpdateRequest(
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
        List<@NotBlank String> issues,

        @NotNull
        @PositiveOrZero
        Long version
) {
}
