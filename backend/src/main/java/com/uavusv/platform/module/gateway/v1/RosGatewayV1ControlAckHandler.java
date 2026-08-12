package com.uavusv.platform.module.gateway.v1;

import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RosGatewayV1ControlAckHandler {

    private static final Logger log = LoggerFactory.getLogger(RosGatewayV1ControlAckHandler.class);
    private static final String SOURCE = "ROS_GATEWAY_V1";

    private final RuntimeControlService runtimeControlService;

    public RosGatewayV1ControlAckHandler(RuntimeControlService runtimeControlService) {
        this.runtimeControlService = runtimeControlService;
    }

    @EventListener
    public void handle(RosGatewayV1ControlAckEvent event) {
        try {
            runtimeControlService.applyGatewayCommandStatus(
                    event.commandKey(), event.runId(), event.status(), event.detail(), event.errorCode(), SOURCE);
        } catch (RuntimeException exception) {
            log.warn("Unable to apply ROS Gateway v1 control state commandKey={} status={} detail={}: {}",
                    event.commandKey(), event.status(), event.detail(), exception.getMessage());
        }
    }
}
