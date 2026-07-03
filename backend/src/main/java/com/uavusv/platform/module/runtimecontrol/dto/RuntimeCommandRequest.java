package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import jakarta.validation.constraints.NotNull;

public record RuntimeCommandRequest(
        @NotNull CommandType commandType,
        String deviceCode,
        String payload,
        String detail
) {
}
