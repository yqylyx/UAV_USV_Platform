package com.uavusv.platform.module.mission;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.dto.response.MissionPreflightResponse;
import com.uavusv.platform.module.mission.entity.MissionExecutionMode;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionTaskDevice;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskDeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskParameterRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.mission.service.impl.MissionServiceImpl;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.data.domain.Pageable;

import java.util.EnumSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class MissionServiceReadModelTests {

    @Mock MissionTaskRepository missionTaskRepository;
    @Mock MissionTaskDeviceRepository missionTaskDeviceRepository;
    @Mock MissionTaskParameterRepository missionTaskParameterRepository;
    @Mock MissionEventRepository missionEventRepository;
    @Mock MissionRunRepository missionRunRepository;
    @Mock DeviceRepository deviceRepository;
    @Mock SimulationSessionRepository simulationSessionRepository;
    @Mock RuntimeControlService runtimeControlService;
    @Mock RuntimeDeviceStatusRepository runtimeDeviceStatusRepository;
    @Mock RuntimeStateService runtimeStateService;

    MissionServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new MissionServiceImpl(missionTaskRepository, missionTaskDeviceRepository,
                missionTaskParameterRepository, missionEventRepository, missionRunRepository,
                deviceRepository, simulationSessionRepository, runtimeControlService,
                runtimeDeviceStatusRepository, runtimeStateService);
    }

    @Test
    void shouldReturnGlobalSummaryExcludingDeletedRows() {
        when(missionTaskRepository.countByDeletedFalse()).thenReturn(8L);
        when(missionTaskRepository.countByDeletedFalseAndStatus(MissionStatus.READY)).thenReturn(3L);
        when(missionTaskRepository.countByDeletedFalseAndStatusIn(EnumSet.of(MissionStatus.RUNNING, MissionStatus.PAUSED))).thenReturn(2L);
        when(missionTaskRepository.countByDeletedFalseAndStatusIn(EnumSet.of(MissionStatus.FAILED, MissionStatus.CANCELLED))).thenReturn(1L);

        var summary = service.getSummary();

        assertEquals(8, summary.total());
        assertEquals(3, summary.ready());
        assertEquals(2, summary.running());
        assertEquals(1, summary.abnormal());
    }

    @ParameterizedTest
    @EnumSource(MissionExecutionMode.class)
    void shouldApplyExecutionModeRequirements(MissionExecutionMode mode) {
        stubReadyMission(mode, DeviceStatus.ONLINE, false);
        when(runtimeStateService.isOnline(anyString())).thenAnswer(invocation -> {
            String code = invocation.getArgument(0);
            return RuntimeStateService.ROS_CODE.equals(code)
                    ? mode != MissionExecutionMode.UNITY_STANDALONE
                    : mode != MissionExecutionMode.ROS_GAZEBO;
        });
        when(runtimeStateService.isUnityOnline(any(), nullable(String.class)))
                .thenReturn(mode != MissionExecutionMode.ROS_GAZEBO);
        when(runtimeStateService.getUnityRuntimeSnapshot(any(), nullable(String.class)))
                .thenReturn(new RuntimeStateService.UnityRuntimeSnapshot(
                        "mission-test", true, Set.of("uav-01"), 12L, LocalDateTime.now()));

        MissionPreflightResponse response = service.preflight(1L);

        assertTrue(response.canStart());
        assertEquals(mode, response.executionMode());
    }

    @Test
    void shouldRejectPreflightWhenRequiredDeviceOffline() {
        stubReadyMission(MissionExecutionMode.UNITY_STANDALONE, DeviceStatus.OFFLINE, false);
        when(runtimeStateService.isOnline(anyString())).thenAnswer(invocation ->
                RuntimeStateService.UNITY_CODE.equals(invocation.getArgument(0)));
        when(runtimeStateService.isUnityOnline(any(), nullable(String.class))).thenReturn(true);
        when(runtimeStateService.getUnityRuntimeSnapshot(any(), nullable(String.class)))
                .thenReturn(new RuntimeStateService.UnityRuntimeSnapshot(
                        "mission-test", true, Set.of(), 12L, LocalDateTime.now()));

        MissionPreflightResponse response = service.preflight(1L);

        assertFalse(response.canStart());
        assertEquals(List.of("uav-01"), response.offlineDeviceCodes());
    }

    @Test
    void shouldRejectPreflightWhenOpenRunExists() {
        stubReadyMission(MissionExecutionMode.UNITY_STANDALONE, DeviceStatus.ONLINE, true);
        when(runtimeStateService.isOnline(anyString())).thenAnswer(invocation ->
                RuntimeStateService.UNITY_CODE.equals(invocation.getArgument(0)));
        when(runtimeStateService.isUnityOnline(any(), nullable(String.class))).thenReturn(true);
        when(runtimeStateService.getUnityRuntimeSnapshot(any(), nullable(String.class)))
                .thenReturn(new RuntimeStateService.UnityRuntimeSnapshot(
                        "mission-test", true, Set.of("uav-01"), 12L, LocalDateTime.now()));

        assertFalse(service.preflight(1L).canStart());
    }

    @Test
    void shouldQueryMissionEventsWithLimit() {
        MissionTask mission = mock(MissionTask.class);
        when(missionTaskRepository.findByIdAndDeletedFalse(1L)).thenReturn(Optional.of(mission));
        when(missionEventRepository.findByMissionIdOrderByOccurredAtDesc(eq(1L), any(Pageable.class))).thenReturn(List.of());

        assertTrue(service.getEvents(1L, null, null, 5).isEmpty());
        verify(missionEventRepository).findByMissionIdOrderByOccurredAtDesc(eq(1L), argThat(page -> page.getPageSize() == 5));
    }

    private void stubReadyMission(MissionExecutionMode mode, DeviceStatus deviceStatus, boolean openRun) {
        MissionTask mission = mock(MissionTask.class);
        when(mission.getExecutionMode()).thenReturn(mode);
        when(mission.getStatus()).thenReturn(MissionStatus.READY);
        when(missionTaskRepository.findByIdAndDeletedFalse(1L)).thenReturn(Optional.of(mission));

        MissionTaskDevice binding = mock(MissionTaskDevice.class);
        when(binding.isRequired()).thenReturn(true);
        when(binding.getDeviceId()).thenReturn(11L);
        when(missionTaskDeviceRepository.findAllByMissionIdOrderByAssignedAtAsc(1L)).thenReturn(List.of(binding));

        Device device = mock(Device.class);
        when(device.getId()).thenReturn(11L);
        lenient().when(device.getCode()).thenReturn("uav-01");
        when(deviceRepository.findAllById(List.of(11L))).thenReturn(List.of(device));

        if (mode != MissionExecutionMode.UNITY_STANDALONE) {
            RuntimeDeviceStatus runtime = mock(RuntimeDeviceStatus.class);
            when(runtime.getDeviceId()).thenReturn(11L);
            when(runtime.getStatus()).thenReturn(deviceStatus);
            when(runtimeDeviceStatusRepository.findAllByDeviceIdIn(List.of(11L))).thenReturn(List.of(runtime));
        }

        when(missionRunRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(eq(1L), anyCollection()))
                .thenReturn(openRun ? Optional.of(mock(MissionRun.class)) : Optional.empty());
    }
}
