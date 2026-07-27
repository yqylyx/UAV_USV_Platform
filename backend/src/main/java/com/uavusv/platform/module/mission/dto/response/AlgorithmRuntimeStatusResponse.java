package com.uavusv.platform.module.mission.dto.response;

import com.fasterxml.jackson.databind.JsonNode;

public record AlgorithmRuntimeStatusResponse(
        Long runId,
        String algorithmCode,
        String state,
        long latestSequence,
        String error,
        JsonNode latestFrame
) {}
