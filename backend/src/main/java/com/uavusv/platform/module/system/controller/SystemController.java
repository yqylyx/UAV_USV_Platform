package com.uavusv.platform.module.system.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.system.dto.response.PlatformComponentResponse;
import com.uavusv.platform.module.system.dto.response.SystemHealthResponse;
import com.uavusv.platform.module.system.service.SystemService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/system")
public class SystemController {

    private final SystemService systemService;

    public SystemController(SystemService systemService) {
        this.systemService = systemService;
    }

    @GetMapping("/health")
    public ApiResponse<SystemHealthResponse> getHealth() {
        return ApiResponse.success(systemService.getHealth());
    }

    @GetMapping("/components")
    public ApiResponse<List<PlatformComponentResponse>> listComponents() {
        return ApiResponse.success(systemService.listComponents());
    }
}
