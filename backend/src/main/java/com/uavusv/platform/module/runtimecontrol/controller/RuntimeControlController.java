package com.uavusv.platform.module.runtimecontrol.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandLogResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandAckRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeControlResponse;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.List;

@RestController
@RequestMapping("/api/runtime-control")
public class RuntimeControlController {
    private final RuntimeControlService runtimeControlService;

    public RuntimeControlController(RuntimeControlService runtimeControlService) {
        this.runtimeControlService = runtimeControlService;
    }

    @GetMapping("/status")
    public ApiResponse<RuntimeControlResponse> status() {
        return ApiResponse.success(runtimeControlService.getStatus());
    }

    @GetMapping("/commands/recent")
    public ApiResponse<List<RuntimeCommandLogResponse>> recentCommands(
            @RequestParam(required = false) Long runId,
            @RequestParam(defaultValue = "100") int limit
    ) {
        return ApiResponse.success(runtimeControlService.recentCommands(runId, limit));
    }

    @PostMapping("/start")
    public ApiResponse<RuntimeControlResponse> start(Authentication authentication) {
        return ApiResponse.success(runtimeControlService.start(authentication.getName()));
    }

    @PostMapping("/stop")
    public ApiResponse<RuntimeControlResponse> stop(Authentication authentication) {
        return ApiResponse.success(runtimeControlService.stop(authentication.getName()));
    }

    @PostMapping("/commands")
    public ApiResponse<RuntimeCommandResponse> issueCommand(
            @Valid @RequestBody RuntimeCommandRequest request,
            Authentication authentication
    ) {
        return ApiResponse.success(runtimeControlService.issueCommand(request, authentication.getName()));
    }

    @PostMapping("/commands/{commandKey}/ack")
    public ApiResponse<RuntimeCommandResponse> acknowledgeCommand(
            @PathVariable String commandKey,
            @Valid @RequestBody RuntimeCommandAckRequest request
    ) {
        return ApiResponse.success(runtimeControlService.acknowledgeCommand(commandKey, request));
    }
}
