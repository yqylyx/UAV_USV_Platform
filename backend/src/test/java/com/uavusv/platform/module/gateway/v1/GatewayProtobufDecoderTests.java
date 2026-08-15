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
    void shouldDecodeDeviceStatusFlightState() {
        UavUsvGatewayV1.DeviceStatus status = UavUsvGatewayV1.DeviceStatus.newBuilder()
                .setDeviceCode("uav_01")
                .setConnectionState("ONLINE")
                .setArmed(false)
                .setActiveCommandId("")
                .setFlightState("GROUNDED")
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("device.status")
                .setSource("uav_usv_fleet_gateway")
                .setDeviceCode("uav_01")
                .setStreamId("device.status.uav_01")
                .setSequence(7)
                .setDeviceStatus(status)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals(GatewayMessageType.DEVICE_STATUS, envelope.type());
        assertEquals("device.status.uav_01", envelope.streamId());
        assertEquals("uav_01", envelope.payload().path("deviceCode").asText());
        assertEquals("ONLINE", envelope.payload().path("connectionState").asText());
        assertEquals("GROUNDED", envelope.payload().path("flightState").asText());
        assertEquals(false, envelope.payload().path("armed").asBoolean());
    }

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

    @Test
    void shouldDecodeControlAckEnvelope() {
        UavUsvGatewayV1.ControlAck ack = UavUsvGatewayV1.ControlAck.newBuilder()
                .setCommandId("command-1")
                .setStatus(UavUsvGatewayV1.ControlStatus.ACCEPTED)
                .setCode("ACCEPTED")
                .setMessage("accepted by ROS")
                .setRetryable(false)
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("control.ack")
                .setSource("uav_usv_fleet_gateway")
                .setStreamId("control")
                .setSequence(43)
                .setControlAck(ack)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals(GatewayMessageType.CONTROL_ACK, envelope.type());
        assertEquals("command-1", envelope.payload().path("commandId").asText());
        assertEquals("ACCEPTED", envelope.payload().path("status").asText());
        assertEquals("ACCEPTED", envelope.payload().path("code").asText());
        assertEquals("accepted by ROS", envelope.payload().path("message").asText());
        assertEquals(false, envelope.payload().path("retryable").asBoolean());
    }

    @Test
    void shouldDecodeControlFeedbackEnvelope() {
        UavUsvGatewayV1.ControlFeedback feedback = UavUsvGatewayV1.ControlFeedback.newBuilder()
                .setCommandId("command-1")
                .setStatus(UavUsvGatewayV1.ControlStatus.EXECUTING)
                .setProgress(0.5f)
                .setPhase("takeoff")
                .setMessage("executing")
                .addActiveDeviceCodes("uav_01")
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("control.feedback")
                .setSource("uav_usv_fleet_gateway")
                .setStreamId("control")
                .setSequence(44)
                .setControlFeedback(feedback)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals(GatewayMessageType.CONTROL_FEEDBACK, envelope.type());
        assertEquals("command-1", envelope.payload().path("commandId").asText());
        assertEquals("EXECUTING", envelope.payload().path("status").asText());
        assertEquals(0.5, envelope.payload().path("progress").asDouble(), 0.0001);
        assertEquals("takeoff", envelope.payload().path("phase").asText());
        assertEquals("executing", envelope.payload().path("message").asText());
        assertEquals("uav_01", envelope.payload().path("activeDeviceCodes").path(0).asText());
    }
}
