package com.uavusv.platform.module.monitoring.integration;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.monitoring.dto.request.IntegrationHeartbeatRequest;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandAckRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

@RestController
@RequestMapping("/api/integration")
public class IntegrationController {

    private final RuntimeStateService runtimeStateService;
    private final RuntimeControlService runtimeControlService;
    private final byte[] expectedToken;

    public IntegrationController(
            RuntimeStateService runtimeStateService,
            RuntimeControlService runtimeControlService,
            @Value("${app.integration.token}") String expectedToken
    ) {
        this.runtimeStateService = runtimeStateService;
        this.runtimeControlService = runtimeControlService;
        this.expectedToken = expectedToken.getBytes(StandardCharsets.UTF_8);
    }

    @PostMapping("/heartbeat")
    public ApiResponse<Map<String, Boolean>> heartbeat(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @Valid @RequestBody IntegrationHeartbeatRequest request,
            HttpServletRequest servletRequest
    ) {
        verifyToken(token);
        if (!RuntimeStateService.UNITY_CODE.equals(request.componentCode())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Unsupported component code");
        }

        runtimeStateService.observeUnityHeartbeat(request, servletRequest.getRemoteAddr());
        return ApiResponse.success(Map.of("accepted", true));
    }

    @PostMapping("/commands/{commandKey}/ack")
    public ApiResponse<RuntimeCommandResponse> acknowledgeCommand(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @PathVariable String commandKey,
            @Valid @RequestBody RuntimeCommandAckRequest request
    ) {
        verifyToken(token);
        return ApiResponse.success(runtimeControlService.acknowledgeCommand(commandKey, request));
    }

    private void verifyToken(String token) {
        if (token == null || !MessageDigest.isEqual(expectedToken, token.getBytes(StandardCharsets.UTF_8))) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED, "Invalid integration token");
        }
    }
}
