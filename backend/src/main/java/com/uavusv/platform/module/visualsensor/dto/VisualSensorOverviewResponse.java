package com.uavusv.platform.module.visualsensor.dto;

import java.util.List;

public record VisualSensorOverviewResponse(
        boolean gatewayConnected,
        String gatewayDetail,
        int onlineCount,
        int totalCount,
        String focusedCameraId,
        List<VisualSensorResponse> sensors
) {
}
