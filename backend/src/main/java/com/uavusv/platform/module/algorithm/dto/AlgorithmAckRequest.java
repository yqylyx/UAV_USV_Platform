package com.uavusv.platform.module.algorithm.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record AlgorithmAckRequest(
        @NotNull Boolean success,
        @Size(max = 1000) String detail,
        @Size(max = 64) String errorCode
) {
}
