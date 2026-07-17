package com.uavusv.platform.module.monitoring.dto.request;

import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.util.List;

public record IntegrationHeartbeatRequest(
        @NotBlank @Size(max = 64) String componentCode,
        @NotBlank @Size(max = 128) String instanceId,
        @NotBlank @Size(max = 32) String state,
        @Size(max = 500) String detail,
        @Size(max = 500) String rosConnectionStatus,
        RuntimeScope runtimeScope,
        Long missionId,
        Long runId,
        Boolean controlsReady,
        List<@Size(max = 64) String> deviceCodes,
        Long trajectorySequence
) {
}
