package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record BatchNodeContentUpdateItem(
        @NotBlank
        @Pattern(regexp = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        String id,
        @NotBlank @Size(max = 255) String title,
        @NotNull @Positive Long expectedNodeVersion
) {
}
