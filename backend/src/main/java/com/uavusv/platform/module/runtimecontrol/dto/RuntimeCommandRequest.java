package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import jakarta.validation.constraints.NotNull;

public record RuntimeCommandRequest(
        @NotNull CommandType commandType,
        Long runId,
        String deviceCode,
        String payload,
        String detail,
        RuntimeScope runtimeScope,
        String runtimeInstanceId
) {
    public RuntimeCommandRequest(
            CommandType commandType,
            Long runId,
            String deviceCode,
            String payload,
            String detail
    ) {
        this(commandType, runId, deviceCode, payload, detail, null, null);
    }
}
