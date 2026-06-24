package com.uavusv.platform.module.mission.service;

import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.module.mission.dto.request.MissionSaveRequest;
import com.uavusv.platform.module.mission.dto.response.MissionDetailResponse;
import com.uavusv.platform.module.mission.dto.response.MissionResponse;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionType;

public interface MissionService {

    PageResponse<MissionResponse> listMissions(
            String keyword,
            MissionType type,
            MissionStatus status,
            int page,
            int size
    );

    MissionDetailResponse getMission(Long id);

    MissionDetailResponse createMission(MissionSaveRequest request);

    MissionDetailResponse updateMission(Long id, MissionSaveRequest request);

    void deleteMission(Long id);
}
