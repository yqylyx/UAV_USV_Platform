package com.uavusv.platform.module.system.dto.response;

import com.uavusv.platform.module.system.entity.PlatformComponent;

public record PlatformComponentResponse(
        Long id,
        String code,
        String name,
        String status
) {
    public static PlatformComponentResponse from(PlatformComponent component) {
        return new PlatformComponentResponse(
                component.getId(),
                component.getCode(),
                component.getName(),
                component.getStatus()
        );
    }
}
