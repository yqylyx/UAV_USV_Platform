package com.uavusv.platform.module.sensor.service;

import java.util.List;

public record RadarScanInput(
        String sensorId,
        long timestampMs,
        double angleMinRad,
        double angleIncrementRad,
        double rangeMinM,
        double rangeMaxM,
        List<Double> rangesM,
        List<Double> intensities
) {
    public RadarScanInput {
        sensorId = sensorId == null || sensorId.isBlank() ? "base_radar" : sensorId.trim();
        rangesM = rangesM == null ? List.of() : List.copyOf(rangesM);
        intensities = intensities == null ? List.of() : List.copyOf(intensities);
    }
}
