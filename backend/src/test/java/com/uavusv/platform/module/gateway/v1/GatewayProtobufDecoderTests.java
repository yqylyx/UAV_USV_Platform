package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.protobuf.Timestamp;
import org.junit.jupiter.api.Test;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class GatewayProtobufDecoderTests {

    private final GatewayProtobufDecoder decoder = new GatewayProtobufDecoder(new ObjectMapper());

    @Test
    void shouldDecodePoseBatchEnvelope() {
        Instant timestamp = Instant.parse("2026-08-09T10:04:16.645841Z");
        UavUsvGatewayV1.Vector3 position = UavUsvGatewayV1.Vector3.newBuilder()
                .setX(-86.9)
                .setY(-222.4)
                .setZ(59.8)
                .build();
        UavUsvGatewayV1.VehiclePoseSample vehicle = UavUsvGatewayV1.VehiclePoseSample.newBuilder()
                .setDeviceCode("uav_01")
                .setLocalPositionEnuM(position)
                .setHeadingDeg(12.5)
                .setFresh(true)
                .setPositionValid(true)
                .build();
        UavUsvGatewayV1.PoseBatch poseBatch = UavUsvGatewayV1.PoseBatch.newBuilder()
                .setSnapshotMode(UavUsvGatewayV1.SnapshotMode.LATEST_STATE)
                .setComplete(true)
                .addExpectedDeviceCodes("uav_01")
                .addVehicles(vehicle)
                .setFreshnessThresholdMs(3000)
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("telemetry.pose_batch")
                .setSource("uav_usv_fleet_gateway")
                .setTimestamp(Timestamp.newBuilder()
                        .setSeconds(timestamp.getEpochSecond())
                        .setNanos(timestamp.getNano()))
                .setRunId("RUN-1")
                .setStreamId("fleet.pose")
                .setSequence(42)
                .setPoseBatch(poseBatch)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals("1.0", envelope.version());
        assertEquals(GatewayMessageType.TELEMETRY_POSE_BATCH, envelope.type());
        assertEquals("uav_usv_fleet_gateway", envelope.source());
        assertEquals(timestamp, envelope.timestamp());
        assertEquals("RUN-1", envelope.runId());
        assertEquals("fleet.pose", envelope.streamId());
        assertEquals(42, envelope.sequence());
        assertEquals(true, envelope.payload().path("complete").asBoolean());
        assertEquals(3000, envelope.payload().path("freshnessThresholdMs").asInt());

        var decodedVehicle = envelope.payload().path("vehicles").path(0);
        assertNotNull(decodedVehicle);
        assertEquals("uav_01", decodedVehicle.path("deviceCode").asText());
        assertEquals(-86.9, decodedVehicle.path("localPositionEnuM").path("x").asDouble(), 0.0001);
        assertEquals(-222.4, decodedVehicle.path("localPositionEnuM").path("y").asDouble(), 0.0001);
        assertEquals(59.8, decodedVehicle.path("localPositionEnuM").path("z").asDouble(), 0.0001);
        assertEquals(12.5, decodedVehicle.path("headingDeg").asDouble(), 0.0001);
        assertEquals(true, decodedVehicle.path("fresh").asBoolean());
        assertEquals(true, decodedVehicle.path("positionValid").asBoolean());
    }
}
