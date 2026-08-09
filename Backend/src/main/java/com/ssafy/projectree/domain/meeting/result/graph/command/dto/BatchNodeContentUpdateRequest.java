package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * REST request for updating up to 100 node titles in one atomic graph command.
 */
public record BatchNodeContentUpdateRequest(
        @NotNull @Size(min = 1, max = 100)
        List<@NotNull @Valid BatchNodeContentUpdateItem> nodes
) {

    @JsonAnySetter
    public void rejectUnsupportedField(String fieldName, Object ignoredValue) {
        throw new IllegalArgumentException(
                "Unsupported batch node title update field: " + fieldName
        );
    }
}
