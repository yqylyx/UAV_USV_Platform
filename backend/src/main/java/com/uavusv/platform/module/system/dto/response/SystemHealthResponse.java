package com.uavusv.platform.module.system.dto.response;

import java.time.Instant;

public record SystemHealthResponse(
        String status,
        String application,
        String database,
        String databaseVersion,
        Instant timestamp
) {
}
