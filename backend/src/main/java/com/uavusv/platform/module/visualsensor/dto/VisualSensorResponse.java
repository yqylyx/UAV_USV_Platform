package com.uavusv.platform.module.visualsensor.dto;

public record VisualSensorResponse(
        String cameraId,
        String deviceCode,
        String deviceType,
        String viewType,
        String displayName,
        String status,
        String source,
        int width,
        int height,
        double fps,
        long latencyMs,
        long timestampMs,
        boolean focused
) {
}
