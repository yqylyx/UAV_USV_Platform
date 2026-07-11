package com.uavusv.platform.module.mission;

import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.mission.service.MissionCommandCoordinator;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MissionCommandCoordinatorTests {

    @Test
    void shouldStartMissionOnlyAfterCommandAcknowledgement() {
        Fixture fixture = fixture();

        fixture.coordinator.handleCommandStatus(new ControlCommandStatusChangedEvent(
                30L, "command-30", 20L, CommandType.START_MISSION,
                CommandStatus.ACKNOWLEDGED, "mock acknowledged", null
        ));

        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.RUNNING, fixture.run.getStatus());
        verify(fixture.eventRepository).save(any());
    }

    @Test
    void shouldKeepMissionReadyWhenStartCommandTimesOut() {
        Fixture fixture = fixture();

        fixture.coordinator.handleCommandStatus(new ControlCommandStatusChangedEvent(
                31L, "command-31", 20L, CommandType.START_MISSION,
                CommandStatus.TIMEOUT, "ack timeout", "ACK_TIMEOUT"
        ));

        assertEquals(MissionStatus.READY, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.FAILED, fixture.run.getStatus());
        assertEquals("ack timeout", fixture.run.getFailureReason());
        assertNotNull(fixture.run.getEndedAt());
        verify(fixture.eventRepository).save(any());
    }

    private Fixture fixture() {
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        MissionTaskRepository taskRepository = mock(MissionTaskRepository.class);
        MissionEventRepository eventRepository = mock(MissionEventRepository.class);
        MissionTask mission = new MissionTask("MT-TEST");
        mission.update(
                "MT-TEST", "测试任务", MissionType.COOPERATIVE_ENCIRCLEMENT,
                MissionStatus.READY, MissionStage.PREPARE, 1,
                "目标", "低速航行", "测试海域", null, null, "状态机测试"
        );
        MissionRun run = new MissionRun(10L, null, 1, MissionStage.TARGET_DETECTED, "admin");
        when(runRepository.findById(20L)).thenReturn(Optional.of(run));
        when(taskRepository.findById(10L)).thenReturn(Optional.of(mission));
        MissionCommandCoordinator coordinator = new MissionCommandCoordinator(runRepository, taskRepository, eventRepository);
        return new Fixture(coordinator, mission, run, eventRepository);
    }

    private record Fixture(
            MissionCommandCoordinator coordinator,
            MissionTask mission,
            MissionRun run,
            MissionEventRepository eventRepository
    ) {
    }
}
