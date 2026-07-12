package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.monitoring.integration.RosPoseWebSocketClient;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.control.command-dispatch-mode", havingValue = "ros-websocket")
public class RosWebSocketCommandDispatcher implements RuntimeCommandDispatcher {

    private final RosPoseWebSocketClient rosWebSocketClient;

    public RosWebSocketCommandDispatcher(RosPoseWebSocketClient rosWebSocketClient) {
        this.rosWebSocketClient = rosWebSocketClient;
    }

    @Override
    public CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request) {
        rosWebSocketClient.sendControlCommand(commandKey, request);
        return CommandDispatchResult.dispatched("Command sent to ROS fleet bridge");
    }
}
