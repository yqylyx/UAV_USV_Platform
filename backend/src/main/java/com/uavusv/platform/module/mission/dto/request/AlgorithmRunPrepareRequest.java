package com.uavusv.platform.module.mission.dto.request;

import jakarta.validation.constraints.NotBlank;

import java.util.Map;

public record AlgorithmRunPrepareRequest(
        @NotBlank String algorithmCode,
        Map<String, Object> config
) {}
