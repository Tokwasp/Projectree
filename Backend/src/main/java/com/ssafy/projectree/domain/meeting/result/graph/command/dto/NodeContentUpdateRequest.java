package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record NodeContentUpdateRequest(
        @Size(max = 255) String title,
        @Size(max = 65535) String content,
        @NotNull @Positive Long expectedNodeVersion
) {
}
