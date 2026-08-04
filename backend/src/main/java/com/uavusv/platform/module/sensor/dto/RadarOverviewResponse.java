package com.uavusv.platform.module.sensor.dto;

import java.util.List;

public record RadarOverviewResponse(
        boolean connected,
        int onlineCount,
        int totalCount,
        long updatedAt,
        int obstacleCount,
        int detectionCount,
        Double nearestObstacleRange,
        String latestTargetId,
        List<RadarItemResponse> items
) {
}
