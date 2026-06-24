package com.uavusv.platform.module.monitoring.integration;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.monitoring.dto.request.IntegrationHeartbeatRequest;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

@RestController
@RequestMapping("/api/integration")
public class IntegrationController {

    private final RuntimeStateService runtimeStateService;
    private final byte[] expectedToken;

    public IntegrationController(
            RuntimeStateService runtimeStateService,
            @Value("${app.integration.token}") String expectedToken
    ) {
        this.runtimeStateService = runtimeStateService;
        this.expectedToken = expectedToken.getBytes(StandardCharsets.UTF_8);
    }

    @PostMapping("/heartbeat")
    public ApiResponse<Map<String, Boolean>> heartbeat(
            @RequestHeader(value = "X-Platform-Token", required = false) String token,
            @Valid @RequestBody IntegrationHeartbeatRequest request,
            HttpServletRequest servletRequest
    ) {
        if (token == null || !MessageDigest.isEqual(expectedToken, token.getBytes(StandardCharsets.UTF_8))) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid integration token");
        }
        if (!RuntimeStateService.UNITY_CODE.equals(request.componentCode())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported component code");
        }

        runtimeStateService.observeUnityHeartbeat(request, servletRequest.getRemoteAddr());
        return ApiResponse.success(Map.of("accepted", true));
    }
}
