package com.uavusv.platform.module.gateway.v1;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DeviceCodeMapperTests {
    private final DeviceCodeMapper mapper = new DeviceCodeMapper();

    @Test void mapsBothBoundariesUniquely() {
        assertEquals("uav-01", mapper.toPlatform("uav_01"));
        assertEquals("usv-03", mapper.toPlatform("USV-03"));
        assertEquals("uav_01", mapper.toRos("uav-01"));
        assertEquals("usv_03", mapper.toRos("usv_03"));
    }

    @Test void rejectsAmbiguousCodes() {
        assertThrows(IllegalArgumentException.class, () -> mapper.toPlatform("UAV01"));
        assertThrows(IllegalArgumentException.class, () -> mapper.toRos("uav-1"));
    }
}
