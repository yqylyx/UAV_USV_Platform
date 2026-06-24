package com.uavusv.platform.module.device.dto.response;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;

import java.time.LocalDateTime;

public record DeviceResponse(
        Long id,
        String code,
        String name,
        DeviceType type,
        DeviceStatus status,
        String host,
        Integer port,
        String rosNamespace,
        String description,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static DeviceResponse from(Device device) {
        return new DeviceResponse(
                device.getId(),
                device.getCode(),
                device.getName(),
                device.getType(),
                device.getStatus(),
                device.getHost(),
                device.getPort(),
                device.getRosNamespace(),
                device.getDescription(),
                device.getCreatedAt(),
                device.getUpdatedAt()
        );
    }
}
