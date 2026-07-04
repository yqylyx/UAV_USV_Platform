package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;

import java.time.LocalDateTime;

public record RuntimeCommandLogResponse(
        Long id,
        Long sessionId,
        CommandType commandType,
        CommandStatus status,
        String requestedBy,
        LocalDateTime requestedAt,
        LocalDateTime completedAt,
        String detail
) {
    public static RuntimeCommandLogResponse from(ControlCommand command) {
        return new RuntimeCommandLogResponse(
                command.getId(),
                command.getSessionId(),
                command.getCommandType(),
                command.getStatus(),
                command.getRequestedBy(),
                command.getRequestedAt(),
                command.getCompletedAt(),
                command.getDetail()
        );
    }
}
