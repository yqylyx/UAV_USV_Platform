package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.protobuf.ByteString;
import com.google.protobuf.Timestamp;
import org.junit.jupiter.api.Test;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.time.Instant;
import java.util.Base64;

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

    @Test
    void shouldDecodeCameraFrameEnvelope() {
        Instant timestamp = Instant.parse("2026-08-16T08:37:44.172044754Z");
        byte[] jpeg = {(byte) 0xff, (byte) 0xd8, 1, 2, (byte) 0xff, (byte) 0xd9};
        UavUsvGatewayV1.CameraFrame cameraFrame = UavUsvGatewayV1.CameraFrame.newBuilder()
                .setCameraId("uav_02_down")
                .setFrameSequence(364)
                .setSourceTimestamp(Timestamp.newBuilder()
                        .setSeconds(timestamp.getEpochSecond())
                        .setNanos(timestamp.getNano()))
                .setWidth(320)
                .setHeight(180)
                .setEncoding("image/jpeg")
                .setJpegData(ByteString.copyFrom(jpeg))
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("media.camera_jpeg")
                .setSource("uav_usv_fleet_gateway")
                .setStreamId("media.camera_jpeg.uav_02_down.boot")
                .setSequence(364)
                .setDeviceCode("uav_02")
                .setFrameId("uav_02/camera_link")
                .setCameraFrame(cameraFrame)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals(GatewayMessageType.MEDIA_CAMERA_JPEG, envelope.type());
        assertEquals("media.camera_jpeg.uav_02_down.boot", envelope.streamId());
        assertEquals(364, envelope.sequence());
        assertEquals("uav_02_down", envelope.payload().path("cameraId").asText());
        assertEquals(364, envelope.payload().path("frameSequence").asLong());
        assertEquals("2026-08-16T08:37:44.172044754Z", envelope.payload().path("sourceTimestamp").asText());
        assertEquals(timestamp.toEpochMilli(), envelope.payload().path("timestampMs").asLong());
        assertEquals(320, envelope.payload().path("width").asInt());
        assertEquals(180, envelope.payload().path("height").asInt());
        assertEquals("image/jpeg", envelope.payload().path("encoding").asText());
        assertEquals(Base64.getEncoder().encodeToString(jpeg), envelope.payload().path("jpegBase64").asText());
        assertEquals(true, envelope.payload().path("jpegBytes").isMissingNode());
    }

    @Test
    void shouldDecodeRadarScanEnvelope() {
        Instant timestamp = Instant.parse("2026-08-16T08:37:44.282487018Z");
        UavUsvGatewayV1.RadarScan radarScan = UavUsvGatewayV1.RadarScan.newBuilder()
                .setSensorId("base_radar")
                .setSensorFrameSequence(243)
                .setSourceTimestamp(Timestamp.newBuilder()
                        .setSeconds(timestamp.getEpochSecond())
                        .setNanos(timestamp.getNano()))
                .setAngleMinRad(-3.1415925f)
                .setAngleMaxRad(3.1415925f)
                .setAngleIncrementRad(0.008738783f)
                .setRangeMinM(3.0f)
                .setRangeMaxM(700.0f)
                .addRangesM(10.0f)
                .addRangesM(Float.POSITIVE_INFINITY)
                .addRangesM(20.0f)
                .addIntensities(1.0f)
                .addIntensities(0.0f)
                .addIntensities(2.0f)
                .build();
        UavUsvGatewayV1.GatewayEnvelope protobufEnvelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("perception.radar_scan")
                .setSource("uav_usv_fleet_gateway")
                .setStreamId("perception.radar_scan.base_radar.boot")
                .setSequence(243)
                .setDeviceCode("base_station")
                .setFrameId("base_radar")
                .setRadarScan(radarScan)
                .build();

        GatewayEnvelope envelope = decoder.decode(protobufEnvelope.toByteArray());

        assertEquals(GatewayMessageType.PERCEPTION_RADAR_SCAN, envelope.type());
        assertEquals("perception.radar_scan.base_radar.boot", envelope.streamId());
        assertEquals(243, envelope.sequence());
        assertEquals("base_radar", envelope.payload().path("sensorId").asText());
        assertEquals(243, envelope.payload().path("sensorFrameSequence").asLong());
        assertEquals("2026-08-16T08:37:44.282487018Z", envelope.payload().path("sourceTimestamp").asText());
        assertEquals(timestamp.toEpochMilli(), envelope.payload().path("timestampMs").asLong());
        assertEquals(-3.1415925, envelope.payload().path("angleMinRad").asDouble(), 0.000001);
        assertEquals(3.1415925, envelope.payload().path("angleMaxRad").asDouble(), 0.000001);
        assertEquals(0.008738783, envelope.payload().path("angleIncrementRad").asDouble(), 0.000001);
        assertEquals(3.0, envelope.payload().path("rangeMinM").asDouble(), 0.0001);
        assertEquals(700.0, envelope.payload().path("rangeMaxM").asDouble(), 0.0001);
        assertEquals(3, envelope.payload().path("rangeCount").asInt());
        assertEquals(3, envelope.payload().path("intensityCount").asInt());
        assertEquals(10.0, envelope.payload().path("rangesM").path(0).asDouble(), 0.0001);
        assertEquals(Double.POSITIVE_INFINITY, envelope.payload().path("rangesM").path(1).asDouble());
        assertEquals(20.0, envelope.payload().path("rangesM").path(2).asDouble(), 0.0001);
        assertEquals(2.0, envelope.payload().path("intensities").path(2).asDouble(), 0.0001);
    }
}
