package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmRunStatus;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record AlgorithmStatusUpdateRequest(
        @NotNull AlgorithmRunStatus status,
        @Size(max = 64) String stage,
        @Size(max = 1000) String message,
        @Size(max = 1000) String errorMessage
) {
}
