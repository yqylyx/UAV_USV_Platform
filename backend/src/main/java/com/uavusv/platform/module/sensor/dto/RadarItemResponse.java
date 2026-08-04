package com.uavusv.platform.module.sensor.dto;

public record RadarItemResponse(
        String id,
        String deviceId,
        String kind,
        Double range,
        Double bearing,
        Double x,
        Double y,
        Double z,
        Double confidence,
        long timestampMs
) {
}
