package com.uavusv.platform.module.mission.dto.response;

public record MissionSummaryResponse(long total, long ready, long running, long abnormal) {
}
