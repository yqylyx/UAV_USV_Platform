package com.uavusv.platform.module.mission.service;

import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.module.mission.dto.request.MissionSaveRequest;
import com.uavusv.platform.module.mission.dto.response.MissionDetailResponse;
import com.uavusv.platform.module.mission.dto.response.MissionActionResponse;
import com.uavusv.platform.module.mission.dto.response.MissionResponse;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.entity.MissionExecutionMode;
import com.uavusv.platform.module.mission.entity.MissionEventLevel;
import com.uavusv.platform.module.mission.dto.response.MissionSummaryResponse;
import com.uavusv.platform.module.mission.dto.response.MissionPreflightResponse;
import com.uavusv.platform.module.mission.dto.response.MissionEventResponse;
import java.util.List;

public interface MissionService {

    PageResponse<MissionResponse> listMissions(
            String keyword,
            MissionType type,
            MissionStatus status,
            MissionExecutionMode executionMode,
            int page,
            int size
    );

    MissionDetailResponse getMission(Long id);

    MissionSummaryResponse getSummary();

    MissionPreflightResponse preflight(Long id, String runtimeInstanceId);

    default MissionPreflightResponse preflight(Long id) {
        return preflight(id, null);
    }

    List<MissionEventResponse> getEvents(Long id, Long runId, MissionEventLevel level, int limit);

    MissionDetailResponse createMission(MissionSaveRequest request);

    MissionDetailResponse updateMission(Long id, MissionSaveRequest request);

    void deleteMission(Long id);

    MissionActionResponse markReady(Long id, String operator, String source);

    MissionActionResponse startMission(Long id, String operator, String source, String runtimeInstanceId);

    MissionActionResponse pauseMission(Long id, String operator, String source);

    MissionActionResponse resumeMission(Long id, String operator, String source);

    MissionActionResponse completeMission(Long id, String operator, String source);

    MissionActionResponse failMission(Long id, String operator, String source);

    MissionActionResponse cancelMission(Long id, String operator, String source);
}
