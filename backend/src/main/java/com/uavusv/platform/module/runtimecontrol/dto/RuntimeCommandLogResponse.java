package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;

import java.time.LocalDateTime;

public record RuntimeCommandLogResponse(
        Long id,
        Long sessionId,
        Long runId,
        Long deviceId,
        String commandKey,
        CommandType commandType,
        RuntimeScope runtimeScope,
        String runtimeInstanceId,
        CommandStatus status,
        String requestedBy,
        LocalDateTime requestedAt,
        LocalDateTime dispatchedAt,
        LocalDateTime acknowledgedAt,
        LocalDateTime completedAt,
        String detail,
        String errorCode
) {
    public static RuntimeCommandLogResponse from(ControlCommand command) {
        return new RuntimeCommandLogResponse(
                command.getId(),
                command.getSessionId(),
                command.getRunId(),
                command.getDeviceId(),
                command.getCommandKey(),
                command.getCommandType(),
                command.getRuntimeScope(),
                command.getRuntimeInstanceId(),
                command.getStatus(),
                command.getRequestedBy(),
                command.getRequestedAt(),
                command.getDispatchedAt(),
                command.getAcknowledgedAt(),
                command.getCompletedAt(),
                command.getDetail(),
                command.getErrorCode()
        );
    }
}
