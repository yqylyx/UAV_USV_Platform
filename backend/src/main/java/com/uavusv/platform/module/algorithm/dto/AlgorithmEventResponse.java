package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmEvent;
import com.uavusv.platform.module.algorithm.entity.AlgorithmEventLevel;
import com.uavusv.platform.module.algorithm.entity.AlgorithmType;

import java.time.LocalDateTime;

public record AlgorithmEventResponse(
        String commandId,
        AlgorithmType algorithmType,
        AlgorithmEventLevel level,
        String stage,
        String message,
        LocalDateTime occurredAt
) {
    public static AlgorithmEventResponse from(AlgorithmEvent event) {
        return new AlgorithmEventResponse(
                event.getCommandId(),
                event.getAlgorithmType(),
                event.getLevel(),
                event.getStage(),
                event.getMessage(),
                event.getOccurredAt()
        );
    }
}
