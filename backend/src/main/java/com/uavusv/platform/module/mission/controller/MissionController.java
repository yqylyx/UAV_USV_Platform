package com.uavusv.platform.module.mission.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.module.mission.dto.request.MissionSaveRequest;
import com.uavusv.platform.module.mission.dto.response.MissionDetailResponse;
import com.uavusv.platform.module.mission.dto.response.MissionResponse;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.service.MissionService;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/missions")
public class MissionController {

    private final MissionService missionService;

    public MissionController(MissionService missionService) {
        this.missionService = missionService;
    }

    @GetMapping
    public ApiResponse<PageResponse<MissionResponse>> listMissions(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) MissionType type,
            @RequestParam(required = false) MissionStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size
    ) {
        return ApiResponse.success(missionService.listMissions(keyword, type, status, page, size));
    }

    @GetMapping("/{id}")
    public ApiResponse<MissionDetailResponse> getMission(@PathVariable Long id) {
        return ApiResponse.success(missionService.getMission(id));
    }

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionDetailResponse> createMission(@Valid @RequestBody MissionSaveRequest request) {
        return ApiResponse.success(missionService.createMission(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionDetailResponse> updateMission(
            @PathVariable Long id,
            @Valid @RequestBody MissionSaveRequest request
    ) {
        return ApiResponse.success(missionService.updateMission(id, request));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Void> deleteMission(@PathVariable Long id) {
        missionService.deleteMission(id);
        return ApiResponse.<Void>success(null);
    }
}
