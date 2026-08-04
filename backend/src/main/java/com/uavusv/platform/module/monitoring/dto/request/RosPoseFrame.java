package com.uavusv.platform.module.monitoring.dto.request;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record RosPoseFrame(
        @JsonProperty("schema_version") Integer schemaVersion,
        @JsonProperty("timestamp_ms") long timestampMs,
        long sequence,
        FleetData fleet,
        List<VehiclePoseData> usvs,
        List<VehiclePoseData> uavs,
        PoseData boat,
        PoseData drone,
        PoseData lighthouse
) {
    public boolean hasFleetVehicles() {
        return (usvs != null && !usvs.isEmpty()) || (uavs != null && !uavs.isEmpty());
    }

    public record FleetData(
            @JsonProperty("expected_usvs") Integer expectedUsvs,
            @JsonProperty("expected_uavs") Integer expectedUavs,
            @JsonProperty("received_usvs") Integer receivedUsvs,
            @JsonProperty("received_uavs") Integer receivedUavs,
            Boolean ready
    ) {
    }

    public record VehiclePoseData(String id, double[] position, double[] orientation) {
        public PoseData poseData() {
            return new PoseData(position, orientation);
        }
    }

    public record PoseData(double[] position, double[] orientation) {
        public boolean valid() {
            return position != null && position.length >= 3 && orientation != null && orientation.length >= 4;
        }
    }
}
