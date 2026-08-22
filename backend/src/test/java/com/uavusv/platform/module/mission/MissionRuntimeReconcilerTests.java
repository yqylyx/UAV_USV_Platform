package com.uavusv.platform.module.mission;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.mission.service.MissionRuntimeReconciler;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MissionRuntimeReconcilerTests {

    @Test
    void startExecutingMovesPendingRunToRunning() {
        Fixture fixture = fixture(MissionStatus.READY, MissionRunStatus.PENDING, 20L);

        fixture.reconciler.reconcileCommandStatus(commandEvent(
                20L, CommandType.START_MISSION, CommandStatus.EXECUTING));

        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.RUNNING, fixture.run.getStatus());
        verify(fixture.eventRepository).save(any(MissionEvent.class));
    }

    @Test
    void duplicateExecutingIsNoOp() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileCommandStatus(commandEvent(
                20L, CommandType.START_MISSION, CommandStatus.EXECUTING));

        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.RUNNING, fixture.run.getStatus());
        verify(fixture.eventRepository, never()).save(any());
    }

    @Test
    void missionStatusCancelledTerminatesMatchingRun() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileMissionStatus("10", "20", "20", "", "CANCELLED", "EVALUATION", "test");

        assertEquals(MissionStatus.CANCELLED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.CANCELLED, fixture.run.getStatus());
        assertNotNull(fixture.run.getEndedAt());
        verify(fixture.eventRepository).save(any(MissionEvent.class));
    }

    @Test
    void cancelMissionCommandCancelledTerminatesMatchingRun() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileCommandStatus(commandEvent(
                20L, CommandType.CANCEL_MISSION, CommandStatus.CANCELLED));

        assertEquals(MissionStatus.CANCELLED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.CANCELLED, fixture.run.getStatus());
        assertNotNull(fixture.run.getEndedAt());
        verify(fixture.eventRepository).save(any(MissionEvent.class));
    }

    @Test
    void duplicateTerminalStatusIsNoOpAndKeepsFinishedAt() {
        Fixture fixture = fixture(MissionStatus.CANCELLED, MissionRunStatus.CANCELLED, 20L);
        LocalDateTime endedAt = fixture.run.getEndedAt();

        fixture.reconciler.reconcileMissionStatus("10", "20", "20", "", "CANCELLED", "EVALUATION", "test");

        assertSame(endedAt, fixture.run.getEndedAt());
        verify(fixture.eventRepository, never()).save(any());
    }

    @Test
    void missionStatusFailedTerminatesMatchingRun() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileMissionStatus("10", "20", "20", "", "FAILED", "TRACKING", "test");

        assertEquals(MissionStatus.FAILED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.FAILED, fixture.run.getStatus());
        assertNotNull(fixture.run.getFailureReason());
    }

    @Test
    void missionStatusCompletedTerminatesMatchingRun() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileMissionStatus("10", "20", "20", "", "COMPLETED", "EVALUATION", "test");

        assertEquals(MissionStatus.COMPLETED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.COMPLETED, fixture.run.getStatus());
    }

    @Test
    void startMissionSucceededOnlyConfirmsStartAndDoesNotCompleteMission() {
        Fixture fixture = fixture(MissionStatus.READY, MissionRunStatus.PENDING, 20L);

        fixture.reconciler.reconcileCommandStatus(commandEvent(
                20L, CommandType.START_MISSION, CommandStatus.SUCCEEDED));

        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.RUNNING, fixture.run.getStatus());
    }

    @Test
    void oldRunTerminalEventDoesNotPolluteCurrentOpenRun() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 4L);
        MissionRun currentRun = run(10L, 5L, MissionRunStatus.RUNNING);
        when(fixture.runRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(eq(10L), anyCollection()))
                .thenReturn(Optional.of(currentRun));

        fixture.reconciler.reconcileMissionStatus("10", "4", "4", "", "CANCELLED", "EVALUATION", "test");

        assertEquals(MissionRunStatus.CANCELLED, fixture.run.getStatus());
        assertEquals(MissionRunStatus.RUNNING, currentRun.getStatus());
        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
    }

    @Test
    void ambiguousRunIdDoesNotChangeDatabaseState() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);

        fixture.reconciler.reconcileMissionStatus("10", "", "", "", "CANCELLED", "EVALUATION", "test");

        assertEquals(MissionStatus.RUNNING, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.RUNNING, fixture.run.getStatus());
        verify(fixture.eventRepository, never()).save(any());
    }

    @Test
    void terminalRunIsNotReopenedByLateExecutingCommand() {
        Fixture fixture = fixture(MissionStatus.CANCELLED, MissionRunStatus.CANCELLED, 20L);

        fixture.reconciler.reconcileCommandStatus(commandEvent(
                20L, CommandType.START_MISSION, CommandStatus.EXECUTING));

        assertEquals(MissionStatus.CANCELLED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.CANCELLED, fixture.run.getStatus());
        verify(fixture.eventRepository, never()).save(any());
    }

    @Test
    void missionStatusCanResolveRunIdThroughActiveCommandId() {
        Fixture fixture = fixture(MissionStatus.RUNNING, MissionRunStatus.RUNNING, 20L);
        ControlCommand command = new ControlCommand(null, 20L, null, CommandType.CANCEL_MISSION,
                null, "operator");
        when(fixture.commandRepository.findByCommandKey("command-20")).thenReturn(Optional.of(command));

        fixture.reconciler.reconcileMissionStatus("10", "", "", "command-20", "CANCELED", "EVALUATION", "test");

        assertEquals(MissionStatus.CANCELLED, fixture.mission.getStatus());
        assertEquals(MissionRunStatus.CANCELLED, fixture.run.getStatus());
    }

    @SuppressWarnings("unchecked")
    private Fixture fixture(MissionStatus missionStatus, MissionRunStatus runStatus, Long runId) {
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        MissionTaskRepository taskRepository = mock(MissionTaskRepository.class);
        MissionEventRepository eventRepository = mock(MissionEventRepository.class);
        ControlCommandRepository commandRepository = mock(ControlCommandRepository.class);
        MissionTask mission = mission(missionStatus);
        MissionRun run = run(10L, runId, runStatus);
        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(taskRepository.findById(10L)).thenReturn(Optional.of(mission));
        when(runRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(
                eq(10L), any(Collection.class))).thenReturn(Optional.empty());
        return new Fixture(
                new MissionRuntimeReconciler(runRepository, taskRepository, eventRepository, commandRepository),
                mission,
                run,
                runRepository,
                eventRepository,
                commandRepository
        );
    }

    private ControlCommandStatusChangedEvent commandEvent(
            Long runId,
            CommandType commandType,
            CommandStatus status
    ) {
        return new ControlCommandStatusChangedEvent(
                30L,
                "command-" + runId,
                runId,
                commandType,
                status,
                "test detail",
                null
        );
    }

    private MissionTask mission(MissionStatus status) {
        MissionTask mission = new MissionTask("MT-TEST");
        mission.update(
                "MT-TEST", "Test mission", MissionType.COOPERATIVE_ENCIRCLEMENT,
                status, status == MissionStatus.READY ? MissionStage.PREPARE : MissionStage.TRACKING, 1,
                "target", "slow", "test area", null, null, "state machine test"
        );
        ReflectionTestUtils.setField(mission, "id", 10L);
        return mission;
    }

    private MissionRun run(Long missionId, Long runId, MissionRunStatus status) {
        MissionRun run = new MissionRun(missionId, null, runId.intValue(), MissionStage.TARGET_DETECTED, "operator");
        ReflectionTestUtils.setField(run, "id", runId);
        switch (status) {
            case RUNNING -> run.activate(MissionStage.TRACKING);
            case PAUSED -> run.pause(MissionStage.TRACKING);
            case COMPLETED -> run.complete(MissionStage.EVALUATION);
            case FAILED -> run.fail(MissionStage.TRACKING, "failed");
            case CANCELLED -> run.cancel(MissionStage.EVALUATION);
            default -> { }
        }
        return run;
    }

    private record Fixture(
            MissionRuntimeReconciler reconciler,
            MissionTask mission,
            MissionRun run,
            MissionRunRepository runRepository,
            MissionEventRepository eventRepository,
            ControlCommandRepository commandRepository
    ) {
    }
}
