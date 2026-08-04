package com.uavusv.platform.module.sensor.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.sensor.dto.RadarOverviewResponse;
import com.uavusv.platform.module.sensor.service.SensorRuntimeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/sensors")
public class SensorController {

    private final SensorRuntimeService sensorRuntimeService;

    public SensorController(SensorRuntimeService sensorRuntimeService) {
        this.sensorRuntimeService = sensorRuntimeService;
    }

    @GetMapping("/radar")
    public ApiResponse<RadarOverviewResponse> radar() {
        return ApiResponse.success(sensorRuntimeService.radarOverview());
    }
}
