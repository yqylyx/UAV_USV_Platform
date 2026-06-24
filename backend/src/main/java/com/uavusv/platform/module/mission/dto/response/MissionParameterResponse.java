package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionTaskParameter;

public record MissionParameterResponse(
        Long id,
        String key,
        String value,
        String unit,
        String description
) {
    public static MissionParameterResponse from(MissionTaskParameter parameter) {
        return new MissionParameterResponse(
                parameter.getId(),
                parameter.getKey(),
                parameter.getValue(),
                parameter.getUnit(),
                parameter.getDescription()
        );
    }
}
