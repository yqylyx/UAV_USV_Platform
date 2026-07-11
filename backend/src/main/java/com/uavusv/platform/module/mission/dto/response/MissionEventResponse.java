package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionEventLevel;
import com.uavusv.platform.module.mission.entity.MissionEventType;
import com.uavusv.platform.module.mission.entity.MissionStage;

import java.time.LocalDateTime;

public record MissionEventResponse(
        Long id,
        Long runId,
        MissionEventType eventType,
        MissionStage stage,
        MissionEventLevel level,
        String title,
        String message,
        String source,
        LocalDateTime occurredAt
) {
    public static MissionEventResponse from(MissionEvent event) {
        return new MissionEventResponse(
                event.getId(),
                event.getRunId(),
                event.getEventType(),
                event.getStage(),
                event.getLevel(),
                event.getTitle(),
                event.getMessage(),
                event.getSource(),
                event.getOccurredAt()
        );
    }
}
