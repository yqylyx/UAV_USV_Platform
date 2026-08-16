package com.uavusv.platform.module.runtimecontrol;

import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class ControlCommandTests {

    @Test
    void shouldKeepAckAndFeedbackNonTerminalUntilResult() {
        ControlCommand command = new ControlCommand(1L, 2L, 3L, CommandType.TAKEOFF, "{}", "admin");

        assertEquals(CommandStatus.PENDING, command.getStatus());
        assertNotNull(command.getCommandKey());
        assertNull(command.getCompletedAt());

        command.dispatch("sent");
        assertEquals(CommandStatus.DISPATCHED, command.getStatus());
        assertNotNull(command.getDispatchedAt());

        command.accept("accepted");
        assertEquals(CommandStatus.ACCEPTED, command.getStatus());
        assertNotNull(command.getAcknowledgedAt());
        assertNull(command.getCompletedAt());

        command.execute("executing");
        assertEquals(CommandStatus.EXECUTING, command.getStatus());
        assertNull(command.getCompletedAt());

        command.succeedResult("done");
        assertEquals(CommandStatus.SUCCEEDED, command.getStatus());
        assertNotNull(command.getCompletedAt());
    }

    @Test
    void shouldNotRegressAfterTerminalResult() {
        ControlCommand command = new ControlCommand(null, CommandType.UAV_HOVER, "admin");
        command.dispatch("sent");
        command.fail("ROS_FAILED", "failed");
        command.accept("late ack");
        command.execute("late feedback");
        command.succeedResult("late success");
        assertEquals(CommandStatus.FAILED, command.getStatus());
        assertEquals("ROS_FAILED", command.getErrorCode());
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
    void rejectedCommandShouldRemainTerminal() {
        ControlCommand command = new ControlCommand(null, CommandType.UAV_TAKEOFF, "admin");

        command.reject("TAKEOFF_ALREADY_IN_PROGRESS", "vehicle takeoff is already in progress");
        command.timeout("late timeout");
        command.succeedResult("late success");

        assertEquals(CommandStatus.REJECTED, command.getStatus());
        assertEquals("TAKEOFF_ALREADY_IN_PROGRESS", command.getErrorCode());
        assertEquals("vehicle takeoff is already in progress", command.getDetail());
        assertNotNull(command.getCompletedAt());
    }

    @Test
    void shouldKeepVehicleSpecificCommandSemantics() {
        ControlCommand uav = new ControlCommand(1L, null, 11L, CommandType.UAV_HOVER, "{}", "admin");
        ControlCommand usv = new ControlCommand(1L, null, 21L, CommandType.USV_HOLD, "{}", "admin");

        assertEquals(CommandType.UAV_HOVER, uav.getCommandType());
        assertEquals(CommandType.USV_HOLD, usv.getCommandType());
        assertEquals(RuntimeScope.SYSTEM_OVERVIEW, uav.getRuntimeScope());
        assertEquals(RuntimeScope.SYSTEM_OVERVIEW, usv.getRuntimeScope());
    }

    @Test
    void shouldBindRunCommandsToMissionCenterInstance() {
        ControlCommand command = new ControlCommand(
                1L,
                20L,
                11L,
                CommandType.START_MISSION,
                "{}",
                "admin",
                RuntimeScope.MISSION_CENTER,
                "mission-unity-test"
        );

        assertEquals(RuntimeScope.MISSION_CENTER, command.getRuntimeScope());
        assertEquals("mission-unity-test", command.getRuntimeInstanceId());
        assertEquals(20L, command.getRunId());
    }
}
