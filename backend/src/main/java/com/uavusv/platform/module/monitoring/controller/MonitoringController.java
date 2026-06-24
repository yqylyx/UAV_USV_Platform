package com.uavusv.platform.module.monitoring.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeNodeResponse;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeSummaryResponse;
import com.uavusv.platform.module.monitoring.service.MonitoringService;
import com.uavusv.platform.module.monitoring.service.RuntimeEventPublisher;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

@RestController
@RequestMapping("/api/monitoring")
public class MonitoringController {

    private final MonitoringService monitoringService;
    private final RuntimeEventPublisher runtimeEventPublisher;

    public MonitoringController(MonitoringService monitoringService, RuntimeEventPublisher runtimeEventPublisher) {
        this.monitoringService = monitoringService;
        this.runtimeEventPublisher = runtimeEventPublisher;
    }

    @GetMapping("/summary")
    public ApiResponse<RuntimeSummaryResponse> getSummary() {
        return ApiResponse.success(monitoringService.getSummary());
    }

    @GetMapping("/nodes")
    public ApiResponse<List<RuntimeNodeResponse>> listRuntimeNodes(
            @RequestParam(required = false) DeviceType type,
            @RequestParam(required = false) DeviceStatus status
    ) {
        return ApiResponse.success(monitoringService.listRuntimeNodes(type, status));
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamRuntimeEvents() {
        return runtimeEventPublisher.subscribe();
    }
}
