package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;

import java.time.LocalDateTime;

public record RuntimeCommandResponse(
        CommandType commandType,
        CommandStatus status,
        String detail,
        LocalDateTime acceptedAt
) {
}
