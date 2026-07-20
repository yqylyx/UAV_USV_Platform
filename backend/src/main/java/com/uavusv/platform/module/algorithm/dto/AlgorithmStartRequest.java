package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmType;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.Map;

public record AlgorithmStartRequest(
        @NotNull AlgorithmType algorithmType,
        @Size(max = 64) String targetId,
        List<String> uavIds,
        List<String> usvIds,
        Map<String, Object> parameters
) {
}
