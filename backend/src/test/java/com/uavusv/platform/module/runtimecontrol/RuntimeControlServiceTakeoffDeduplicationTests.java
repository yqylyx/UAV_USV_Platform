package com.uavusv.platform.module.runtimecontrol;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dispatch.CommandDispatchResult;
import com.uavusv.platform.module.runtimecontrol.dispatch.RuntimeCommandDispatcher;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import java.util.Collection;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RuntimeControlServiceTakeoffDeduplicationTests {
    private ControlCommandRepository commandRepository;
    private RuntimeCommandDispatcher commandDispatcher;
    private MissionRunRepository missionRunRepository;
    private RuntimeStateService runtimeStateService;
    private RuntimeControlService service;

    @BeforeEach
    void setUp() {
        commandRepository = mock(ControlCommandRepository.class);
        commandDispatcher = mock(RuntimeCommandDispatcher.class);
        missionRunRepository = mock(MissionRunRepository.class);
        DeviceRepository deviceRepository = mock(DeviceRepository.class);
        Device device = mock(Device.class);
        when(device.getId()).thenReturn(11L);
        when(device.getType()).thenReturn(DeviceType.UAV);
        when(deviceRepository.findByCode("uav-01")).thenReturn(Optional.of(device));
        when(commandRepository.save(any(ControlCommand.class))).thenAnswer(invocation -> invocation.getArgument(0));
        runtimeStateService = mock(RuntimeStateService.class);
        service = new RuntimeControlService(
                runtimeStateService,
                mock(SimulationSessionRepository.class),
                commandRepository,
                deviceRepository,
                missionRunRepository,
                commandDispatcher,
                mock(ApplicationEventPublisher.class),
                "Ubuntu", ".", ".", ".", "ws://localhost", "token", "ros-gateway-v1", 15, 75
        );
    }

    @Test
    void systemOverviewDuplicateTakeoffIsRejectedWithoutDispatch() {
        when(commandRepository.existsByDeviceIdAndCommandTypeAndStatusIn(
                eq(11L), eq(CommandType.UAV_TAKEOFF), any())).thenReturn(true);

        RuntimeCommandResponse response = service.issueCommand(request(null, RuntimeScope.SYSTEM_OVERVIEW), "test");

        assertEquals(CommandStatus.REJECTED, response.status());
        assertEquals("TAKEOFF_ALREADY_IN_PROGRESS", response.errorCode());
        assertEquals("vehicle takeoff is already in progress", response.detail());
        verify(commandDispatcher, never()).dispatch(any(), any());
    }

    @Test
    void missionCenterDuplicateTakeoffIsRejectedWithoutDispatch() {
        when(missionRunRepository.existsById(21L)).thenReturn(true);
        when(commandRepository.existsByDeviceIdAndCommandTypeAndStatusIn(
                eq(11L), eq(CommandType.UAV_TAKEOFF), any())).thenReturn(true);

        RuntimeCommandResponse response = service.issueCommand(request(21L, RuntimeScope.MISSION_CENTER), "test");

        assertEquals(CommandStatus.REJECTED, response.status());
        assertEquals("TAKEOFF_ALREADY_IN_PROGRESS", response.errorCode());
        verify(commandDispatcher, never()).dispatch(any(), any());
    }

    @Test
    void terminalTakeoffHistoryDoesNotBlockAnotherTakeoff() {
        when(commandRepository.existsByDeviceIdAndCommandTypeAndStatusIn(
                eq(11L), eq(CommandType.UAV_TAKEOFF), any())).thenReturn(false);
        when(commandDispatcher.dispatch(any(), any())).thenReturn(CommandDispatchResult.dispatched("sent"));

        RuntimeCommandResponse response = service.issueCommand(request(null, RuntimeScope.SYSTEM_OVERVIEW), "test");

        assertEquals(CommandStatus.DISPATCHED, response.status());
        verify(commandDispatcher).dispatch(any(), any());
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Collection<CommandStatus>> statuses = ArgumentCaptor.forClass(Collection.class);
        verify(commandRepository).existsByDeviceIdAndCommandTypeAndStatusIn(
                eq(11L), eq(CommandType.UAV_TAKEOFF), statuses.capture());
        assertEquals(4, statuses.getValue().size());
        assertFalse(statuses.getValue().contains(CommandStatus.REJECTED));
        assertFalse(statuses.getValue().contains(CommandStatus.SUCCEEDED));
        assertFalse(statuses.getValue().contains(CommandStatus.FAILED));
        assertFalse(statuses.getValue().contains(CommandStatus.TIMEOUT));
        assertFalse(statuses.getValue().contains(CommandStatus.CANCELLED));
    }

    @Test
    void airborneTakeoffIsRejectedWithoutDispatch() {
        when(commandRepository.existsByDeviceIdAndCommandTypeAndStatusIn(
                eq(11L), eq(CommandType.UAV_TAKEOFF), any())).thenReturn(false);
        when(runtimeStateService.getUavTakeoffReadiness("uav-01")).thenReturn(
                new RuntimeStateService.TakeoffReadiness(
                        false,
                        "UAV_ALREADY_AIRBORNE",
                        "UAV takeoff rejected because current altitude is 19.80 m",
                        "AIRBORNE",
                        19.8
                )
        );

        RuntimeCommandResponse response = service.issueCommand(request(null, RuntimeScope.SYSTEM_OVERVIEW), "test");

        assertEquals(CommandStatus.REJECTED, response.status());
        assertEquals("UAV_ALREADY_AIRBORNE", response.errorCode());
        verify(commandDispatcher, never()).dispatch(any(), any());
    }

    @Test
    void otherVehicleCommandKeepsExistingDispatchBehavior() {
        when(commandDispatcher.dispatch(any(), any())).thenReturn(CommandDispatchResult.dispatched("sent"));
        RuntimeCommandRequest hover = new RuntimeCommandRequest(
                CommandType.UAV_HOVER, null, "uav-01", "{}", "hover",
                RuntimeScope.SYSTEM_OVERVIEW, null);

        RuntimeCommandResponse response = service.issueCommand(hover, "test");

        assertEquals(CommandStatus.DISPATCHED, response.status());
        verify(commandRepository, never()).existsByDeviceIdAndCommandTypeAndStatusIn(
                anyLong(), any(), any());
        verify(commandDispatcher).dispatch(any(), any());
    }

    private RuntimeCommandRequest request(Long runId, RuntimeScope scope) {
        return new RuntimeCommandRequest(
                CommandType.UAV_TAKEOFF, runId, "uav-01", "{}", "takeoff", scope, null);
    }
}
