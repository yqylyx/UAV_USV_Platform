package com.uavusv.platform.module.mission.dto.response;

import java.util.List;

public record MissionDetailResponse(
        MissionResponse mission,
        List<MissionDeviceResponse> devices,
        List<MissionParameterResponse> parameters,
        List<MissionEventResponse> events,
        MissionRunResponse currentRun,
        List<MissionRunResponse> runs
) {
}
