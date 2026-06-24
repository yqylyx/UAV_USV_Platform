package com.uavusv.platform.module.monitoring.dto.request;

import com.fasterxml.jackson.annotation.JsonProperty;

public record RosPoseFrame(
        @JsonProperty("timestamp_ms") long timestampMs,
        long sequence,
        PoseData boat,
        PoseData drone,
        PoseData lighthouse
) {
    public record PoseData(double[] position, double[] orientation) {
        public boolean valid() {
            return position != null && position.length >= 3 && orientation != null && orientation.length >= 4;
        }
    }
}
