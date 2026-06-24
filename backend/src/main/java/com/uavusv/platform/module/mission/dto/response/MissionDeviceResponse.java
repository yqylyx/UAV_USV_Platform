package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.mission.entity.MissionDeviceRole;
import com.uavusv.platform.module.mission.entity.MissionTaskDevice;

import java.time.LocalDateTime;

public record MissionDeviceResponse(
        Long id,
        Long deviceId,
        String code,
        String name,
        DeviceType type,
        DeviceStatus status,
        MissionDeviceRole role,
        String callSign,
        boolean required,
        LocalDateTime assignedAt,
        String notes
) {
    public static MissionDeviceResponse from(MissionTaskDevice binding, Device device) {
        return new MissionDeviceResponse(
                binding.getId(),
                binding.getDeviceId(),
                device == null ? null : device.getCode(),
                device == null ? null : device.getName(),
                device == null ? null : device.getType(),
                device == null ? null : device.getStatus(),
                binding.getRole(),
                binding.getCallSign(),
                binding.isRequired(),
                binding.getAssignedAt(),
                binding.getNotes()
        );
    }
}
