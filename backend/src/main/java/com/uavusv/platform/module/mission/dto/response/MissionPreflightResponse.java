package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.mission.entity.MissionExecutionMode;
import com.uavusv.platform.module.mission.entity.MissionStatus;

import java.time.LocalDateTime;
import java.util.List;

public record MissionPreflightResponse(
        Long missionId,
        MissionStatus missionStatus,
        MissionExecutionMode executionMode,
        boolean configurationComplete,
        int requiredDeviceCount,
        int onlineRequiredDeviceCount,
        List<String> offlineDeviceCodes,
        boolean rosOnline,
        boolean unityOnline,
        boolean unityControlsReady,
        int unityRecognizedDeviceCount,
        Long unityTrajectorySequence,
        boolean hasOpenRun,
        boolean canStart,
        List<MissionPreflightIssueResponse> issues,
        LocalDateTime checkedAt
) {
}
