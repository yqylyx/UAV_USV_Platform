package com.uavusv.platform.module.runtimecontrol.event;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;

public record ControlCommandStatusChangedEvent(
        Long commandId,
        String commandKey,
        Long runId,
        CommandType commandType,
        CommandStatus status,
        String detail,
        String errorCode
) {
}
