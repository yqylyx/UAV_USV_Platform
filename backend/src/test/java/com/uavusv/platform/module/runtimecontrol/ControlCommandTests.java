package com.uavusv.platform.module.runtimecontrol;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class ControlCommandTests {

    @Test
    void shouldTrackDispatchAndAcknowledgement() {
        ControlCommand command = new ControlCommand(1L, 2L, 3L, CommandType.TAKEOFF, "{}", "admin");

        assertEquals(CommandStatus.PENDING, command.getStatus());
        assertNotNull(command.getCommandKey());
        assertNull(command.getCompletedAt());

        command.dispatch("sent");
        assertEquals(CommandStatus.DISPATCHED, command.getStatus());
        assertNotNull(command.getDispatchedAt());

        command.acknowledge("accepted");
        assertEquals(CommandStatus.ACKNOWLEDGED, command.getStatus());
        assertNotNull(command.getAcknowledgedAt());
        assertNotNull(command.getCompletedAt());
    }

    @Test
    void shouldTrackTimeoutSeparatelyFromFailure() {
        ControlCommand command = new ControlCommand(null, CommandType.START_MISSION, "admin");
        command.dispatch("sent");

        command.timeout("ack timeout");

        assertEquals(CommandStatus.TIMEOUT, command.getStatus());
        assertEquals("ACK_TIMEOUT", command.getErrorCode());
        assertNotNull(command.getCompletedAt());
    }

    @Test
    void shouldKeepVehicleSpecificCommandSemantics() {
        ControlCommand uav = new ControlCommand(1L, null, 11L, CommandType.UAV_HOVER, "{}", "admin");
        ControlCommand usv = new ControlCommand(1L, null, 21L, CommandType.USV_HOLD, "{}", "admin");

        assertEquals(CommandType.UAV_HOVER, uav.getCommandType());
        assertEquals(CommandType.USV_HOLD, usv.getCommandType());
    }
}
