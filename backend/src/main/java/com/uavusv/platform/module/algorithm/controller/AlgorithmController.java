package com.uavusv.platform.module.algorithm.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.common.integration.IntegrationTokenVerifier;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAckRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAssignmentsResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAssignmentsUpdateRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmEventRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmEventResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmRunResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStartRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStatusUpdateRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStopRequest;
import com.uavusv.platform.module.algorithm.service.AlgorithmService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/algorithm")
public class AlgorithmController {

    private final AlgorithmService algorithmService;
    private final IntegrationTokenVerifier tokenVerifier;

    public AlgorithmController(AlgorithmService algorithmService, IntegrationTokenVerifier tokenVerifier) {
        this.algorithmService = algorithmService;
        this.tokenVerifier = tokenVerifier;
    }

    @PostMapping("/start")
    public ApiResponse<AlgorithmRunResponse> start(@Valid @RequestBody AlgorithmStartRequest request) {
        return ApiResponse.success(algorithmService.start(request));
    }

    @PostMapping("/stop")
    public ApiResponse<List<AlgorithmRunResponse>> stop(@Valid @RequestBody(required = false) AlgorithmStopRequest request) {
        return ApiResponse.success(algorithmService.stop(request));
    }

    @GetMapping("/status")
    public ApiResponse<List<AlgorithmRunResponse>> status(@RequestParam(required = false) String commandId) {
        return ApiResponse.success(algorithmService.status(commandId));
    }

    @GetMapping("/assignments")
    public ApiResponse<AlgorithmAssignmentsResponse> assignments(@RequestParam(required = false) String commandId) {
        return ApiResponse.success(algorithmService.assignments(commandId));
    }

    @GetMapping("/events")
    public ApiResponse<List<AlgorithmEventResponse>> events(@RequestParam(required = false) String commandId) {
        return ApiResponse.success(algorithmService.events(commandId));
    }

    @PostMapping("/{commandId}/ack")
    public ApiResponse<AlgorithmRunResponse> acknowledge(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @PathVariable String commandId,
            @Valid @RequestBody AlgorithmAckRequest request,
            Authentication authentication
    ) {
        tokenVerifier.verifyAuthenticatedOrToken(authentication, token);
        return ApiResponse.success(algorithmService.acknowledge(commandId, request));
    }

    @PostMapping("/{commandId}/status")
    public ApiResponse<AlgorithmRunResponse> updateStatus(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @PathVariable String commandId,
            @Valid @RequestBody AlgorithmStatusUpdateRequest request,
            Authentication authentication
    ) {
        tokenVerifier.verifyAuthenticatedOrToken(authentication, token);
        return ApiResponse.success(algorithmService.updateStatus(commandId, request));
    }

    @PostMapping("/{commandId}/assignments")
    public ApiResponse<AlgorithmAssignmentsResponse> updateAssignments(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @PathVariable String commandId,
            @Valid @RequestBody AlgorithmAssignmentsUpdateRequest request,
            Authentication authentication
    ) {
        tokenVerifier.verifyAuthenticatedOrToken(authentication, token);
        return ApiResponse.success(algorithmService.updateAssignments(commandId, request));
    }

    @PostMapping("/events")
    public ApiResponse<AlgorithmEventResponse> appendEvent(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @Valid @RequestBody AlgorithmEventRequest request,
            Authentication authentication
    ) {
        tokenVerifier.verifyAuthenticatedOrToken(authentication, token);
        return ApiResponse.success(algorithmService.appendEvent(request));
    }
}
