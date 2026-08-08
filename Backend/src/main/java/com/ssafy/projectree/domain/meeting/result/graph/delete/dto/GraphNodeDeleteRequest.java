package com.ssafy.projectree.domain.meeting.result.graph.delete.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.util.List;

public record GraphNodeDeleteRequest(
        @NotNull
        @Size(min = 1, max = 1000)
        List<
                @NotNull
                @NotBlank
                @Pattern(regexp = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
                String
                > nodeIds,
        @PositiveOrZero long expectedGraphVersion
) {
}
