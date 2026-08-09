package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

public record BatchNodeContentUpdateRequest(
        @NotNull @Size(min = 1, max = 100)
        List<@NotNull @Valid BatchNodeContentUpdateItem> nodes
) {
}
