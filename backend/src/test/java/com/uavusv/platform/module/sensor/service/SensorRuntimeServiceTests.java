package com.uavusv.platform.module.sensor.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SensorRuntimeServiceTests {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void summarizesLatestRadarFrameWithoutPersistence() throws Exception {
        SensorRuntimeService service = new SensorRuntimeService();
        service.observeRadarFrame(objectMapper.readTree("""
                {
                  "type": "radar_frame",
                  "device_id": "usv_01",
                  "timestamp_ms": 2000,
                  "obstacles": [
                    {"id": "obs-1", "range": 12.6, "bearing": -15.3}
                  ],
                  "detections": [
                    {"id": "target-1", "range": 20.0, "confidence": 0.91}
                  ]
                }
                """));

        var overview = service.radarOverview();

        assertThat(overview.connected()).isTrue();
        assertThat(overview.onlineCount()).isEqualTo(1);
        assertThat(overview.obstacleCount()).isEqualTo(1);
        assertThat(overview.detectionCount()).isEqualTo(1);
        assertThat(overview.nearestObstacleRange()).isEqualTo(12.6);
        assertThat(overview.latestTargetId()).isEqualTo("target-1");
    }

    @Test
    void summarizesPointCloudFrameAsRadarPoints() throws Exception {
        SensorRuntimeService service = new SensorRuntimeService();
        service.observePointCloudFrame(objectMapper.readTree("""
                {
                  "schema_version": "1.0",
                  "message_type": "pointcloud_frame",
                  "timestamp": 1784692800.5,
                  "sequence": 1,
                  "source": "uav_usv_fleet_gateway",
                  "data": {
                    "stream_id": "usv_01_mid360",
                    "vehicle_id": "usv_01",
                    "frame_id": "usv_01/mid360_link",
                    "timestamp": 1784692800.25,
                    "point_count": 4,
                    "xyz": [
                      4.125, -1.25, 0.45,
                      4.375, -1.0, 0.475,
                      4.625, -0.75, 0.5,
                      4.875, -0.5, 0.525
                    ]
                  }
                }
                """));

        var overview = service.radarOverview();

        assertThat(overview.connected()).isTrue();
        assertThat(overview.onlineCount()).isEqualTo(1);
        assertThat(overview.detectionCount()).isEqualTo(4);
        assertThat(overview.items()).hasSize(4);
        assertThat(overview.items().get(0).kind()).isEqualTo("POINTCLOUD");
        assertThat(overview.items().get(0).deviceId()).isEqualTo("usv_01");
        assertThat(overview.items().get(0).x()).isEqualTo(4.125);
        assertThat(overview.items().get(0).y()).isEqualTo(-1.25);
        assertThat(overview.items().get(0).z()).isEqualTo(0.45);
        assertThat(overview.items().get(0).timestampMs()).isEqualTo(1784692800250L);
    }
}
