package com.uavusv.platform.module.mission.dto.response;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

public record AlgorithmRuntimeStatusResponse(
        Long runId,
        String algorithmCode,
        String state,
        long latestSequence,
        String error,
        JsonNode latestFrame,
        String runtimeRef,
        String runtimeGeneration,
        String protocolVersion,
        List<String> capabilities
) {
    public AlgorithmRuntimeStatusResponse {
        capabilities = capabilities == null ? List.of() : List.copyOf(capabilities);
    }

    /** Legacy and Unity-native callers keep the original response fields. */
    public AlgorithmRuntimeStatusResponse(Long runId, String algorithmCode, String state,
            long latestSequence, String error, JsonNode latestFrame) {
        this(runId, algorithmCode, state, latestSequence, error, latestFrame,
                null, null, null, List.of());
    }
}
