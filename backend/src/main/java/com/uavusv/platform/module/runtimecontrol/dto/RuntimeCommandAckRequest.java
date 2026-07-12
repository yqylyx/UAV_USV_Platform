package com.uavusv.platform.module.runtimecontrol.dto;

import jakarta.validation.constraints.NotNull;

public record RuntimeCommandAckRequest(
        @NotNull Boolean success,
        String detail,
        String errorCode,
        String source
) {
}
