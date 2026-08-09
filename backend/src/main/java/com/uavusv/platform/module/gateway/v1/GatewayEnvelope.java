package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.databind.JsonNode;

import java.time.Instant;

public record GatewayEnvelope(
        String version,
        GatewayMessageType type,
        String source,
        Instant timestamp,
        String runId,
        String streamId,
        long sequence,
        JsonNode payload
) {
    @JsonIgnore
    public boolean isTelemetryPoseBatch() {
        return type == GatewayMessageType.TELEMETRY_POSE_BATCH;
    }

    @JsonIgnore
    public boolean isMissionStatus() {
        return type == GatewayMessageType.MISSION_STATUS;
    }
}
