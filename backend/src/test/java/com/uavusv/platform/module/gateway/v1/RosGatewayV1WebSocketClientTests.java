package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;

class RosGatewayV1WebSocketClientTests {

    private final ObjectMapper objectMapper = new ObjectMapper();

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

    private byte[] syntheticJpeg(int length) {
        byte[] jpeg = new byte[length];
        jpeg[0] = (byte) 0xff;
        jpeg[1] = (byte) 0xd8;
        jpeg[length - 2] = (byte) 0xff;
        jpeg[length - 1] = (byte) 0xd9;
        return jpeg;
    }
}
