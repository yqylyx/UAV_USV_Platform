package com.uavusv.platform.module.algorithm.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import java.util.List;

public record AlgorithmAssignmentsUpdateRequest(
        @Size(max = 64) String targetId,
        @NotEmpty List<@Valid AlgorithmAssignmentItemRequest> assignments
) {
}
