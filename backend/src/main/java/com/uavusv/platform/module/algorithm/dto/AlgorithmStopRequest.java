package com.uavusv.platform.module.algorithm.dto;

import jakarta.validation.constraints.Size;

public record AlgorithmStopRequest(
        @Size(max = 64) String commandId,
        @Size(max = 1000) String reason
) {
}
