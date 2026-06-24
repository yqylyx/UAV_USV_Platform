package com.uavusv.platform.module.monitoring.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record IntegrationHeartbeatRequest(
        @NotBlank @Size(max = 64) String componentCode,
        @NotBlank @Size(max = 128) String instanceId,
        @NotBlank @Size(max = 32) String state,
        @Size(max = 500) String detail,
        @Size(max = 500) String rosConnectionStatus
) {
}
