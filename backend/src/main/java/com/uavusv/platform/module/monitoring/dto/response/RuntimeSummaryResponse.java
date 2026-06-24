package com.uavusv.platform.module.monitoring.dto.response;

import java.time.LocalDateTime;

public record RuntimeSummaryResponse(
        long totalNodes,
        long onlineNodes,
        long offlineNodes,
        long warningNodes,
        long unknownNodes,
        long rosNodes,
        long unityNodes,
        long vehicleNodes,
        LocalDateTime refreshedAt
) {
}
