package com.uavusv.platform.module.gateway.v1;

import com.uavusv.platform.common.api.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/gateway/v1/debug")
public class GatewayV1DebugController {

    private final RealtimeHub realtimeHub;

    public GatewayV1DebugController(RealtimeHub realtimeHub) {
        this.realtimeHub = realtimeHub;
    }

    @GetMapping("/snapshot")
    public ApiResponse<RealtimeHub.RealtimeSnapshot> snapshot() {
        return ApiResponse.success(realtimeHub.snapshot());
    }

    @GetMapping("/pose-batch")
    public ApiResponse<GatewayEnvelope> latestPoseBatch() {
        return ApiResponse.success(realtimeHub.latestPoseBatch().orElse(null));
    }

    @GetMapping("/mission-status")
    public ApiResponse<GatewayEnvelope> latestMissionStatus() {
        return ApiResponse.success(realtimeHub.latestMissionStatus().orElse(null));
    }
}
