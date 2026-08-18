package com.uavusv.platform.config;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public class RosCommunicationPropertiesValidator {
    private final String transport;
    private final String authority;
    private final String dispatchMode;

    public RosCommunicationPropertiesValidator(
            @Value("${app.ros.transport:v1}") String transport,
            @Value("${app.ros.state-authority:v1}") String authority,
            @Value("${app.control.command-dispatch-mode:browser-unity}") String dispatchMode) {
        this.transport = transport.toLowerCase();
        this.authority = authority.toLowerCase();
        this.dispatchMode = dispatchMode.toLowerCase();
    }

    @PostConstruct
    void validate() {
        if (!Set.of("legacy", "v1", "dual-test").contains(transport)) {
            throw new IllegalStateException("Unsupported app.ros.transport: " + transport);
        }
        if (!Set.of("legacy", "v1").contains(authority)
                || (!"dual-test".equals(transport) && !transport.equals(authority))) {
            throw new IllegalStateException("app.ros.state-authority must select an enabled ROS transport");
        }
        if ("legacy".equals(transport) && "ros-gateway-v1".equals(dispatchMode)) {
            throw new IllegalStateException("legacy transport cannot use ros-gateway-v1 command dispatch");
        }
        if ("v1".equals(transport) && "ros-websocket".equals(dispatchMode)) {
            throw new IllegalStateException("v1 transport cannot use legacy ros-websocket command dispatch");
        }
    }
}
