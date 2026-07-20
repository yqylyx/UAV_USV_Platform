package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmRun;
import com.uavusv.platform.module.algorithm.entity.AlgorithmRunStatus;
import com.uavusv.platform.module.algorithm.entity.AlgorithmType;

import java.time.LocalDateTime;

public record AlgorithmRunResponse(
        String commandId,
        AlgorithmType algorithmType,
        AlgorithmRunStatus status,
        String targetId,
        String stage,
        String message,
        LocalDateTime startedAt,
        LocalDateTime lastAckAt,
        LocalDateTime completedAt,
        LocalDateTime updatedAt,
        String errorMessage
) {
    public static AlgorithmRunResponse from(AlgorithmRun run) {
        return new AlgorithmRunResponse(
                run.getCommandId(),
                run.getAlgorithmType(),
                run.getStatus(),
                run.getTargetId(),
                run.getStage(),
                run.getMessage(),
                run.getStartedAt(),
                run.getLastAckAt(),
                run.getCompletedAt(),
                run.getUpdatedAt(),
                run.getErrorMessage()
        );
    }
}
