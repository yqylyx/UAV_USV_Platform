package com.uavusv.platform.module.runtimecontrol.service;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandAckRequest;
import com.uavusv.platform.module.runtimecontrol.event.RosCommandAckReceivedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RosCommandAckListener {

    private final RuntimeControlService runtimeControlService;

    public RosCommandAckListener(RuntimeControlService runtimeControlService) {
        this.runtimeControlService = runtimeControlService;
    }

    @EventListener
    public void handle(RosCommandAckReceivedEvent event) {
        if (event.commandKey() == null || event.commandKey().isBlank()) return;
        if (event.status() == 1 || event.status() == 3) {
            runtimeControlService.acknowledgeCommand(event.commandKey(),
                    new RuntimeCommandAckRequest(true, event.message(), null, "ROS"));
        } else if (event.status() == 4 || event.status() == 5 || event.status() == 6) {
            runtimeControlService.acknowledgeCommand(event.commandKey(),
                    new RuntimeCommandAckRequest(false, event.message(), "ROS_COMMAND_REJECTED", "ROS"));
        }
    }
}
