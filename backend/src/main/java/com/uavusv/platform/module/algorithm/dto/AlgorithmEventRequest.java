package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmEventLevel;
import com.uavusv.platform.module.algorithm.entity.AlgorithmType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AlgorithmEventRequest(
        @Size(max = 64) String commandId,
        AlgorithmType algorithmType,
        AlgorithmEventLevel level,
        @Size(max = 64) String stage,
        @NotBlank @Size(max = 1000) String message
) {
}
