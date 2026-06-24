package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionEventType;

import java.time.LocalDateTime;

public record MissionEventResponse(
        Long id,
        MissionEventType eventType,
        String title,
        String message,
        String source,
        LocalDateTime occurredAt
) {
    public static MissionEventResponse from(MissionEvent event) {
        return new MissionEventResponse(
                event.getId(),
                event.getEventType(),
                event.getTitle(),
                event.getMessage(),
                event.getSource(),
                event.getOccurredAt()
        );
    }
}
