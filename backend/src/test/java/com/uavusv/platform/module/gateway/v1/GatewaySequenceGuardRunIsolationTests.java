package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GatewaySequenceGuardRunIsolationTests {
    private final GatewaySequenceGuard guard = new GatewaySequenceGuard();
    private final ObjectMapper mapper = new ObjectMapper();

    @Test void keepsTaskSequencesIndependentByRun() {
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(envelope("A", 100)).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(envelope("B", 1)).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(envelope("A", 101)).status());
    }

    @Test void acceptsSystemPoseWithoutRunId() {
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(envelope(null, 1)).status());
    }

    @Test void rejectsMissionStatusWithoutRunId() {
        GatewayEnvelope status = new GatewayEnvelope("1.0", GatewayMessageType.MISSION_STATUS,
                "ros", Instant.now(), null, "mission", 1, mapper.createObjectNode());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.OLD_RUN, guard.inspect(status).status());
    }

    @Test void acceptsSystemControlAckWithoutRunIdAndKeepsSequenceChecks() {
        GatewayEnvelope first = controlAck(null, 2);
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(first).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.DUPLICATE, guard.inspect(first).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.OUT_OF_ORDER, guard.inspect(controlAck(null, 1)).status());
    }

    @Test void keepsDeviceStatusSequencesIndependentPerStream() {
        GatewayEnvelope uav1 = deviceStatus("device.status.uav_01", 8);
        GatewayEnvelope uav2 = deviceStatus("device.status.uav_02", 1);
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(uav1).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.ACCEPTED, guard.inspect(uav2).status());
        assertEquals(GatewaySequenceGuard.SequenceCheckStatus.DUPLICATE, guard.inspect(uav1).status());
    }

    private GatewayEnvelope envelope(String runId, long sequence) {
        return new GatewayEnvelope("1.0", GatewayMessageType.TELEMETRY_POSE_BATCH,
                "ros", Instant.now(), runId, "pose", sequence, mapper.createObjectNode());
    }

    private GatewayEnvelope controlAck(String runId, long sequence) {
        return new GatewayEnvelope("1.0", GatewayMessageType.CONTROL_ACK,
                "ros", Instant.now(), runId, "control", sequence, mapper.createObjectNode());
    }

    private GatewayEnvelope deviceStatus(String streamId, long sequence) {
        return new GatewayEnvelope("1.0", GatewayMessageType.DEVICE_STATUS,
                "ros", Instant.now(), null, streamId, sequence, mapper.createObjectNode());
    }
}
