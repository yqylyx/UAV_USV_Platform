package com.uavusv.platform.module.runtimecontrol.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeControlResponse;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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

    @PostMapping("/start")
    public ApiResponse<RuntimeControlResponse> start(Authentication authentication) {
        return ApiResponse.success(runtimeControlService.start(authentication.getName()));
    }

    @PostMapping("/stop")
    public ApiResponse<RuntimeControlResponse> stop(Authentication authentication) {
        return ApiResponse.success(runtimeControlService.stop(authentication.getName()));
    }
}
