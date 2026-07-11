package com.uavusv.platform.module.mission.dto.response;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;

public record MissionActionResponse(
        MissionDetailResponse detail,
        RuntimeCommandResponse command
) {
}
