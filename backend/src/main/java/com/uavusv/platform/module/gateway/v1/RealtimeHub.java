package com.uavusv.platform.module.gateway.v1;

import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class RealtimeHub {

    private final AtomicReference<GatewayEnvelope> latestPoseBatch = new AtomicReference<>();
    private final AtomicReference<GatewayEnvelope> latestMissionStatus = new AtomicReference<>();
    private final RealtimeWebSocketHandler realtimeWebSocketHandler;

    public RealtimeHub(RealtimeWebSocketHandler realtimeWebSocketHandler) {
        this.realtimeWebSocketHandler = realtimeWebSocketHandler;
    }

    public void publish(GatewayEnvelope envelope) {
        if (envelope.isTelemetryPoseBatch()) {
            latestPoseBatch.set(envelope);
        } else if (envelope.isMissionStatus()) {
            latestMissionStatus.set(envelope);
        }
        if (shouldBroadcast(envelope.type())) {
            realtimeWebSocketHandler.broadcast(envelope);
        }
    }

    public Optional<GatewayEnvelope> latestPoseBatch() {
        return Optional.ofNullable(latestPoseBatch.get());
    }

    public Optional<GatewayEnvelope> latestMissionStatus() {
        return Optional.ofNullable(latestMissionStatus.get());
    }

    public RealtimeSnapshot snapshot() {
        return new RealtimeSnapshot(latestPoseBatch.get(), latestMissionStatus.get());
    }

    private boolean shouldBroadcast(GatewayMessageType type) {
        return type == GatewayMessageType.TELEMETRY_POSE_BATCH
                || type == GatewayMessageType.MISSION_STATUS
                || type == GatewayMessageType.CONTROL_ACK
                || type == GatewayMessageType.CONTROL_FEEDBACK
                || type == GatewayMessageType.CONTROL_RESULT;
    }

    public record RealtimeSnapshot(
            GatewayEnvelope latestPoseBatch,
            GatewayEnvelope latestMissionStatus
    ) {
    }
}
