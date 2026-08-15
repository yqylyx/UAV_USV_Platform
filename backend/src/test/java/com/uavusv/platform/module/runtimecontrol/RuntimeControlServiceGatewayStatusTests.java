package com.uavusv.platform.module.runtimecontrol;

import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dispatch.RuntimeCommandDispatcher;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class RuntimeControlServiceGatewayStatusTests {
    private ControlCommandRepository commandRepository;
    private RuntimeCommandDispatcher commandDispatcher;
    private RuntimeControlService service;

    @BeforeEach
    void setUp() {
        commandRepository = mock(ControlCommandRepository.class);
        commandDispatcher = mock(RuntimeCommandDispatcher.class);
        service = new RuntimeControlService(
                mock(RuntimeStateService.class),
                mock(SimulationSessionRepository.class),
                commandRepository,
                mock(DeviceRepository.class),
                mock(MissionRunRepository.class),
                commandDispatcher,
                mock(ApplicationEventPublisher.class),
                "Ubuntu", ".", ".", ".", "ws://localhost", "token", "ros-gateway-v1", 15,75
        );
    }

    @Test
    void selectDeviceIsRejectedBeforeGatewayDispatch() {
        RuntimeCommandRequest request = new RuntimeCommandRequest(
                CommandType.SELECT_DEVICE, null, "usv-01", "{}", "select device"
        );

        BusinessException exception = assertThrows(
                BusinessException.class,
                () -> service.issueCommand(request, "test")
        );

        assertEquals(ErrorCode.INVALID_COMMAND_SCOPE, exception.getErrorCode());
        assertEquals("Command SELECT_DEVICE is not a ROS control command", exception.getMessage());
        verifyNoInteractions(commandRepository, commandDispatcher);
    }

    @Test
    void systemOverviewRejectWithoutRunIdRemainsRejected() {
        ControlCommand command = command(null, RuntimeScope.SYSTEM_OVERVIEW);

        service.applyGatewayCommandStatus(command.getCommandKey(), null, "REJECTED",
                "vehicle is already airborne", "VEHICLE_ALREADY_AIRBORNE", "ROS_GATEWAY_V1");

        assertEquals(CommandStatus.REJECTED, command.getStatus());
        assertEquals("VEHICLE_ALREADY_AIRBORNE", command.getErrorCode());
        assertEquals("vehicle is already airborne", command.getDetail());
        verify(commandRepository).save(command);
    }

    @Test
    void systemOverviewResponseWithRunIdFailsAsUnexpected() {
        ControlCommand command = command(null, RuntimeScope.SYSTEM_OVERVIEW);

        service.applyGatewayCommandStatus(command.getCommandKey(), "123", "ACCEPTED",
                "accepted", null, "ROS_GATEWAY_V1");

        assertEquals(CommandStatus.FAILED, command.getStatus());
        assertEquals("UNEXPECTED_RUN_ID", command.getErrorCode());
    }

    @Test
    void missionCenterResponseWithMatchingRunIdIsAccepted() {
        ControlCommand command = command(123L, RuntimeScope.MISSION_CENTER);

        service.applyGatewayCommandStatus(command.getCommandKey(), "123", "ACCEPTED",
                "accepted", null, "ROS_GATEWAY_V1");

        assertEquals(CommandStatus.ACCEPTED, command.getStatus());
    }

    @Test
    void missionCenterResponseWithoutRunIdFailsAsMissing() {
        ControlCommand command = command(123L, RuntimeScope.MISSION_CENTER);

        service.applyGatewayCommandStatus(command.getCommandKey(), null, "ACCEPTED",
                "accepted", null, "ROS_GATEWAY_V1");

        assertEquals(CommandStatus.FAILED, command.getStatus());
        assertEquals("RUN_ID_MISSING", command.getErrorCode());
    }

    @Test
    void missionCenterResponseWithDifferentRunIdFailsAsMismatch() {
        ControlCommand command = command(123L, RuntimeScope.MISSION_CENTER);

        service.applyGatewayCommandStatus(command.getCommandKey(), "456", "ACCEPTED",
                "accepted", null, "ROS_GATEWAY_V1");

        assertEquals(CommandStatus.FAILED, command.getStatus());
        assertEquals("RUN_ID_MISMATCH", command.getErrorCode());
    }

    private ControlCommand command(Long runId, RuntimeScope scope) {
        ControlCommand command = new ControlCommand(
                1L, runId, 2L, CommandType.USV_HOLD, "{}", "test", scope, "instance");
        command.dispatch("dispatched");
        when(commandRepository.findByCommandKey(command.getCommandKey())).thenReturn(Optional.of(command));
        when(commandRepository.save(command)).thenReturn(command);
        return command;
    }
}
