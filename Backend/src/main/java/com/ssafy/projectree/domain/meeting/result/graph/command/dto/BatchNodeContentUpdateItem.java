package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.ssafy.projectree.global.validation.TrimmedSize;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;

/**
 * Frontend title-only batch update item. Content and graphVersion are not part of this contract.
 */
public record BatchNodeContentUpdateItem(
        @NotBlank
        @Pattern(regexp = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        String id,
        @NotBlank @TrimmedSize(max = 255) String title,
        @NotNull @Positive Long expectedNodeVersion
) {

    @JsonAnySetter
    public void rejectUnsupportedField(String fieldName, Object ignoredValue) {
        throw new IllegalArgumentException(
                "Unsupported batch node title update field: " + fieldName
        );
    }
}
