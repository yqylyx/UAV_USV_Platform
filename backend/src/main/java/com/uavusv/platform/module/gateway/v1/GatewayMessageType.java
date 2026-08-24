package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Arrays;

public enum GatewayMessageType {
    GATEWAY_HELLO("gateway.hello"),
    GATEWAY_HEARTBEAT("gateway.heartbeat"),
    DEVICE_STATUS("device.status"),
    TELEMETRY_POSE_BATCH("telemetry.pose_batch"),
    MISSION_STATUS("mission.status"),
    MEDIA_CAMERA_JPEG("media.camera_jpeg"),
    PERCEPTION_RADAR_SCAN("perception.radar_scan"),
    CONTROL_COMMAND("control.command"),
    CONTROL_ACK("control.ack"),
    CONTROL_FEEDBACK("control.feedback"),
    CONTROL_RESULT("control.result");

    private final String wireName;

    GatewayMessageType(String wireName) {
        this.wireName = wireName;
    }

    @JsonValue
    public String wireName() {
        return wireName;
    }

    public static GatewayMessageType fromWireName(String value) {
        String normalized = value == null ? "" : value.trim();
        if ("telemetry.device_status".equals(normalized)) {
            return DEVICE_STATUS;
        }
        return Arrays.stream(values())
                .filter(type -> type.wireName.equals(normalized))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unsupported gateway message type: " + normalized));
    }
}
