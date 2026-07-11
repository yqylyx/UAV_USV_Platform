package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;

import java.time.LocalDateTime;

public record MissionRunResponse(
        Long id,
        Long sessionId,
        String runKey,
        Integer runNo,
        MissionRunStatus status,
        MissionStage stage,
        String requestedBy,
        LocalDateTime startedAt,
        LocalDateTime pausedAt,
        LocalDateTime endedAt,
        String failureReason
) {
    public static MissionRunResponse from(MissionRun run) {
        return new MissionRunResponse(
                run.getId(),
                run.getSessionId(),
                run.getRunKey(),
                run.getRunNo(),
                run.getStatus(),
                run.getStage(),
                run.getRequestedBy(),
                run.getStartedAt(),
                run.getPausedAt(),
                run.getEndedAt(),
                run.getFailureReason()
        );
    }
}
