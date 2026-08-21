package com.uavusv.platform.module.mission.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.mission.dto.request.AlgorithmRunPrepareRequest;
import com.uavusv.platform.module.mission.dto.request.ThreatPlacementRequest;
import com.uavusv.platform.module.mission.dto.response.AlgorithmRuntimeStatusResponse;
import com.uavusv.platform.module.mission.service.AlgorithmRuntimeManager;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/algorithm-runs")
public class AlgorithmRuntimeController {
    private final AlgorithmRuntimeManager manager;

    public AlgorithmRuntimeController(AlgorithmRuntimeManager manager) { this.manager = manager; }

    @PostMapping("/{runId}/prepare")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmRuntimeStatusResponse> prepare(@PathVariable Long runId, @Valid @RequestBody AlgorithmRunPrepareRequest request) {
        return ApiResponse.success(manager.prepare(runId, request.algorithmCode(), request.config()));
    }

    @PostMapping("/{runId}/{action:start|pause|resume|cancel|stop}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmRuntimeStatusResponse> action(@PathVariable Long runId, @PathVariable String action) {
        return ApiResponse.success(manager.action(runId, action));
    }

    @PostMapping("/{runId}/threat")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmRuntimeStatusResponse> placeThreat(@PathVariable Long runId, @Valid @RequestBody ThreatPlacementRequest request) {
        return ApiResponse.success(manager.placeThreat(runId, request.x(), request.y()));
    }

    @PostMapping("/{runId}/active-capture")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmRuntimeStatusResponse> activateCapture(
            @PathVariable Long runId,
            @RequestParam(required = false) String threatCode) {
        return ApiResponse.success(manager.activateCapture(runId, threatCode));
    }

    @GetMapping("/{runId}/status")
    public ApiResponse<AlgorithmRuntimeStatusResponse> status(@PathVariable Long runId) {
        return ApiResponse.success(manager.status(runId));
    }

    @GetMapping("/{runId}/frame")
    public ApiResponse<JsonNode> frame(@PathVariable Long runId, @RequestParam(defaultValue = "0") long afterSequence) {
        return ApiResponse.success(manager.latestFrame(runId, afterSequence));
    }

    @GetMapping("/{runId}/frames")
    public ApiResponse<List<JsonNode>> frames(@PathVariable Long runId, @RequestParam(defaultValue = "0") long afterSequence) {
        return ApiResponse.success(manager.framesAfter(runId, afterSequence));
    }
}
