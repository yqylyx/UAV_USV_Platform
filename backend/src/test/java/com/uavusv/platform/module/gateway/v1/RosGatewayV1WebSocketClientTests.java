package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.protobuf.Timestamp;
import com.uavusv.platform.module.mission.service.MissionRuntimeReconciler;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.sensor.service.SensorRuntimeService;
import com.uavusv.platform.module.visualsensor.service.VisualSensorService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class RosGatewayV1WebSocketClientTests {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private ApplicationEventPublisher eventPublisher;
    private MissionRuntimeReconciler missionRuntimeReconciler;

    @BeforeEach
    void setUp() {
        eventPublisher = mock(ApplicationEventPublisher.class);
        missionRuntimeReconciler = mock(MissionRuntimeReconciler.class);
    }

    @Test
    void readsSnakeCaseCameraJpegPayloadFromGatewayJson() throws Exception {
        assertSnakeCaseCameraPayload("uav_03", 1587);
        assertSnakeCaseCameraPayload("usv_03", 3031);
    }

    private void assertSnakeCaseCameraPayload(String cameraId, int jpegBytes) throws Exception {
        byte[] jpeg = syntheticJpeg(jpegBytes);
        var payload = objectMapper.readTree("""
                {
                  "camera_id": "%s",
                  "jpeg_data": "%s",
                  "width": 320,
                  "height": 180,
                  "timestamp_ms": 1786900000123
                }
                """.formatted(cameraId, Base64.getEncoder().encodeToString(jpeg)));
        var envelope = new GatewayEnvelope(
                "1.0",
                GatewayMessageType.MEDIA_CAMERA_JPEG,
                "uav_usv_fleet_gateway",
                Instant.parse("2026-08-16T08:37:44Z"),
                null,
                "media.camera_jpeg." + cameraId + ".boot",
                377,
                payload
        );

        var camera = RosGatewayV1WebSocketClient.cameraJpegPayload(envelope);

        assertThat(camera.cameraId()).isEqualTo(cameraId);
        assertThat(Base64.getDecoder().decode(camera.jpegBase64())).isEqualTo(jpeg);
        assertThat(camera.width()).isEqualTo(320);
        assertThat(camera.height()).isEqualTo(180);
        assertThat(camera.timestampMs()).isEqualTo(1786900000123L);
    }

    @Test
    void publishesControlFeedbackToCommandStateHandler() {
        RosGatewayV1WebSocketClient client = new RosGatewayV1WebSocketClient(
                mock(GatewayEnvelopeDecoder.class),
                new GatewayProtobufDecoder(objectMapper),
                new GatewaySequenceGuard(),
                mock(RealtimeHub.class),
                eventPublisher,
                mock(RuntimeStateService.class),
                missionRuntimeReconciler,
                mock(VisualSensorService.class),
                mock(SensorRuntimeService.class),
                "ws://127.0.0.1:8765/uav_usv/v1",
                "v1"
        );
        WebSocket socket = mock(WebSocket.class);
        UavUsvGatewayV1.ControlFeedback feedback = UavUsvGatewayV1.ControlFeedback.newBuilder()
                .setCommandId("command-1")
                .setStatus(UavUsvGatewayV1.ControlStatus.EXECUTING)
                .setMessage("executing")
                .build();
        UavUsvGatewayV1.GatewayEnvelope envelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("control.feedback")
                .setSource("uav_usv_fleet_gateway")
                .setTimestamp(Timestamp.newBuilder().setSeconds(1786900000))
                .setRunId("12")
                .setStreamId("control")
                .setSequence(1)
                .setControlFeedback(feedback)
                .build();

        client.onBinary(socket, ByteBuffer.wrap(envelope.toByteArray()), true);

        verify(eventPublisher).publishEvent(new RosGatewayV1ControlAckEvent(
                "command-1",
                "12",
                "EXECUTING",
                "executing",
                null
        ));
        verify(socket).request(1);
    }

    @Test
    void reconcilesMissionStatusFromGateway() {
        RosGatewayV1WebSocketClient client = new RosGatewayV1WebSocketClient(
                mock(GatewayEnvelopeDecoder.class),
                new GatewayProtobufDecoder(objectMapper),
                new GatewaySequenceGuard(),
                mock(RealtimeHub.class),
                eventPublisher,
                mock(RuntimeStateService.class),
                missionRuntimeReconciler,
                mock(VisualSensorService.class),
                mock(SensorRuntimeService.class),
                "ws://127.0.0.1:8765/uav_usv/v1",
                "v1"
        );
        WebSocket socket = mock(WebSocket.class);
        UavUsvGatewayV1.MissionStatus missionStatus = UavUsvGatewayV1.MissionStatus.newBuilder()
                .setMissionId("10")
                .setRunId("20")
                .setState("COMPLETED")
                .setPhase("EVALUATION")
                .setActiveCommandId("command-20")
                .build();
        UavUsvGatewayV1.GatewayEnvelope envelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion("1.0")
                .setMessageType("mission.status")
                .setSource("uav_usv_fleet_gateway")
                .setTimestamp(Timestamp.newBuilder().setSeconds(1786900000))
                .setRunId("20")
                .setStreamId("mission")
                .setSequence(1)
                .setMissionStatus(missionStatus)
                .build();

        client.onBinary(socket, ByteBuffer.wrap(envelope.toByteArray()), true);

        verify(missionRuntimeReconciler).reconcileMissionStatus(
                "10",
                "20",
                "20",
                "command-20",
                "COMPLETED",
                "EVALUATION",
                "ROS_GATEWAY_V1"
        );
        verify(socket).request(1);
    }

    private byte[] syntheticJpeg(int length) {
        byte[] jpeg = new byte[length];
        jpeg[0] = (byte) 0xff;
        jpeg[1] = (byte) 0xd8;
        jpeg[length - 2] = (byte) 0xff;
        jpeg[length - 1] = (byte) 0xd9;
        return jpeg;
    }
}
