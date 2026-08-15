package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Arrays;

public enum GatewayMessageType {
    GATEWAY_HELLO("gateway.hello"),
    GATEWAY_HEARTBEAT("gateway.heartbeat"),
    DEVICE_STATUS("device.status"),
    TELEMETRY_POSE_BATCH("telemetry.pose_batch"),
    MISSION_STATUS("mission.status"),
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
        return Arrays.stream(values())
                .filter(type -> type.wireName.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unsupported gateway message type: " + value));
    }
}
