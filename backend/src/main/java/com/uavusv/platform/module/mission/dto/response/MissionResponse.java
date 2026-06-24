package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionType;

import java.time.LocalDateTime;

public record MissionResponse(
        Long id,
        String code,
        String name,
        MissionType type,
        MissionStatus status,
        MissionStage stage,
        Integer priority,
        String targetName,
        String targetBehavior,
        String missionArea,
        LocalDateTime plannedStartAt,
        LocalDateTime plannedEndAt,
        String description,
        int deviceCount,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static MissionResponse from(MissionTask mission, int deviceCount) {
        return new MissionResponse(
                mission.getId(),
                mission.getCode(),
                mission.getName(),
                mission.getType(),
                mission.getStatus(),
                mission.getStage(),
                mission.getPriority(),
                mission.getTargetName(),
                mission.getTargetBehavior(),
                mission.getMissionArea(),
                mission.getPlannedStartAt(),
                mission.getPlannedEndAt(),
                mission.getDescription(),
                deviceCount,
                mission.getCreatedAt(),
                mission.getUpdatedAt()
        );
    }
}
