package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.monitoring.integration.RosPoseWebSocketClient;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.control.command-dispatch-mode", havingValue = "ros-websocket")
public class RosWebSocketCommandDispatcher implements RuntimeCommandDispatcher {

    private static final Logger log = LoggerFactory.getLogger(RosWebSocketCommandDispatcher.class);

    private final RosPoseWebSocketClient rosWebSocketClient;

    public RosWebSocketCommandDispatcher(RosPoseWebSocketClient rosWebSocketClient) {
        this.rosWebSocketClient = rosWebSocketClient;
    }

    @Override
    public CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request) {
        log.info("[runtime-control-dispatcher] mode=ros-websocket commandKey={} commandType={} deviceCode={} scope={}",
                commandKey, request.commandType(), request.deviceCode(), request.runtimeScope());
        rosWebSocketClient.sendControlCommand(commandKey, request);
        log.info("[runtime-control-dispatcher] mode=ros-websocket sent commandKey={}", commandKey);
        return CommandDispatchResult.dispatched("Command sent to ROS fleet bridge");
    }
}
