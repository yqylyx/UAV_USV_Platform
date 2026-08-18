package com.uavusv.platform.module.monitoring.dto.request;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RosPoseFrameTests {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void parsesFleetVehicleArraysFromBridgeFrame() throws Exception {
        String json = """
                {
                  "type": "pose_frame",
                  "schema_version": 2,
                  "timestamp_ms": 1000,
                  "sequence": 7,
                  "target": {"id": "enemy_ship"},
                  "fleet": {
                    "expected_usvs": 3,
                    "expected_uavs": 3,
                    "received_usvs": 3,
                    "received_uavs": 3,
                    "ready": true
                  },
                  "usvs": [
                    {"id": "usv_01", "position": [1, 2, 3], "orientation": [0, 0, 0, 1]}
                  ],
                  "uavs": [
                    {"id": "uav_01", "position": [4, 5, 6], "orientation": [0, 0, 0, 1]}
                  ]
                }
                """;

        RosPoseFrame frame = objectMapper.readValue(json, RosPoseFrame.class);

        assertThat(frame.schemaVersion()).isEqualTo(2);
        assertThat(frame.hasFleetVehicles()).isTrue();
        assertThat(frame.fleet().ready()).isTrue();
        assertThat(frame.usvs()).extracting(RosPoseFrame.VehiclePoseData::id).containsExactly("usv_01");
        assertThat(frame.uavs()).extracting(RosPoseFrame.VehiclePoseData::id).containsExactly("uav_01");
    }
}
