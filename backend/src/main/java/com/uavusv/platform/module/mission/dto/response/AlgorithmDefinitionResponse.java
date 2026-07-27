package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.AlgorithmDefinition;
import com.uavusv.platform.module.mission.entity.MissionType;

public record AlgorithmDefinitionResponse(
        Long id,
        String code,
        String name,
        String version,
        MissionType missionType,
        String adapterType,
        String deviceScale,
        boolean enabled,
        boolean defaultForType,
        String description
) {
    public static AlgorithmDefinitionResponse from(AlgorithmDefinition value) {
        return new AlgorithmDefinitionResponse(value.getId(), value.getCode(), value.getName(), value.getVersion(),
                value.getMissionType(), value.getAdapterType(), value.getDeviceScale(), value.isEnabled(),
                value.isDefaultForType(), value.getDescription());
    }
}
