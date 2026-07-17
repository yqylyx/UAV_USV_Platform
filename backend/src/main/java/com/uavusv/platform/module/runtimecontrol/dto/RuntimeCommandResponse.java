package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;

import java.time.LocalDateTime;

public record RuntimeCommandResponse(
        Long id,
        String commandKey,
        CommandType commandType,
        RuntimeScope runtimeScope,
        String runtimeInstanceId,
        CommandStatus status,
        String detail,
        LocalDateTime acceptedAt
) {
    public static RuntimeCommandResponse from(com.uavusv.platform.module.runtimecontrol.entity.ControlCommand command) {
        return new RuntimeCommandResponse(
                command.getId(),
                command.getCommandKey(),
                command.getCommandType(),
                command.getRuntimeScope(),
                command.getRuntimeInstanceId(),
                command.getStatus(),
                command.getDetail(),
                command.getRequestedAt()
        );
    }
}
