package com.uavusv.platform.module.mission.controller;

import com.uavusv.platform.common.api.ApiResponse;
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
import com.uavusv.platform.module.mission.service.MissionService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
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
            @RequestParam(required = false) MissionExecutionMode executionMode,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size
    ) {
        return ApiResponse.success(missionService.listMissions(keyword, type, status, executionMode, page, size));
    }

    @GetMapping("/summary")
    public ApiResponse<MissionSummaryResponse> summary() {
        return ApiResponse.success(missionService.getSummary());
    }

    @GetMapping("/{id}")
    public ApiResponse<MissionDetailResponse> getMission(@PathVariable Long id) {
        return ApiResponse.success(missionService.getMission(id));
    }

    @GetMapping("/{id}/preflight")
    public ApiResponse<MissionPreflightResponse> preflight(
            @PathVariable Long id,
            @RequestParam(required = false) String runtimeInstanceId
    ) {
        return ApiResponse.success(missionService.preflight(id, runtimeInstanceId));
    }

    @GetMapping("/{id}/events")
    public ApiResponse<List<MissionEventResponse>> events(
            @PathVariable Long id,
            @RequestParam(required = false) Long runId,
            @RequestParam(required = false) MissionEventLevel level,
            @RequestParam(defaultValue = "20") int limit
    ) {
        return ApiResponse.success(missionService.getEvents(id, runId, level, limit));
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

    @PostMapping("/{id}/ready")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> markReady(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.markReady(id, authentication.getName(), source));
    }

    @PostMapping("/{id}/start")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> startMission(
            @PathVariable Long id,
            @RequestParam(defaultValue = "UNKNOWN") String source,
            @RequestParam(required = false) String runtimeInstanceId,
            Authentication authentication
    ) {
        return ApiResponse.success(missionService.startMission(id, authentication.getName(), source, runtimeInstanceId));
    }

    @PostMapping("/{id}/pause")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> pauseMission(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.pauseMission(id, authentication.getName(), source));
    }

    @PostMapping("/{id}/resume")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> resumeMission(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.resumeMission(id, authentication.getName(), source));
    }

    @PostMapping("/{id}/complete")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> completeMission(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.completeMission(id, authentication.getName(), source));
    }

    @PostMapping("/{id}/fail")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> failMission(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.failMission(id, authentication.getName(), source));
    }

    @PostMapping("/{id}/cancel")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<MissionActionResponse> cancelMission(@PathVariable Long id, @RequestParam(defaultValue = "UNKNOWN") String source, Authentication authentication) {
        return ApiResponse.success(missionService.cancelMission(id, authentication.getName(), source));
    }
}
