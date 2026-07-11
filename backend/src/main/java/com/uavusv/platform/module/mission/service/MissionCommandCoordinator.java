package com.uavusv.platform.module.mission.service;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionEventLevel;
import com.uavusv.platform.module.mission.entity.MissionEventType;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class MissionCommandCoordinator {

    private final MissionRunRepository missionRunRepository;
    private final MissionTaskRepository missionTaskRepository;
    private final MissionEventRepository missionEventRepository;

    public MissionCommandCoordinator(
            MissionRunRepository missionRunRepository,
            MissionTaskRepository missionTaskRepository,
            MissionEventRepository missionEventRepository
    ) {
        this.missionRunRepository = missionRunRepository;
        this.missionTaskRepository = missionTaskRepository;
        this.missionEventRepository = missionEventRepository;
    }

    @EventListener
    @Transactional
    public void handleCommandStatus(ControlCommandStatusChangedEvent event) {
        if (event.runId() == null || !isMissionAction(event.commandType())) {
            return;
        }

        MissionRun run = missionRunRepository.findById(event.runId()).orElse(null);
        if (run == null) {
            return;
        }
        MissionTask mission = missionTaskRepository.findById(run.getMissionId()).orElse(null);
        if (mission == null || mission.isDeleted()) {
            return;
        }

        if (event.status() == CommandStatus.ACKNOWLEDGED) {
            applyAcknowledgedAction(mission, run, event);
        } else if (event.status() == CommandStatus.FAILED || event.status() == CommandStatus.TIMEOUT) {
            applyRejectedAction(mission, run, event);
        }
    }

    private void applyAcknowledgedAction(
            MissionTask mission,
            MissionRun run,
            ControlCommandStatusChangedEvent event
    ) {
        boolean changed = switch (event.commandType()) {
            case START_MISSION -> activate(mission, run);
            case PAUSE_MISSION -> pause(mission, run);
            case RESUME_MISSION -> resume(mission, run);
            case COMPLETE_MISSION -> complete(mission, run);
            case FAIL_MISSION -> fail(mission, run, event.detail());
            case CANCEL_MISSION -> cancel(mission, run);
            default -> false;
        };

        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run.getId(),
                changed ? MissionEventType.STATUS : MissionEventType.ALERT,
                mission.getStage(),
                changed ? MissionEventLevel.INFO : MissionEventLevel.WARNING,
                changed ? "控制指令已确认" : "控制指令未改变任务状态",
                commandDescription(event),
                "command:" + event.commandKey()
        ));
    }

    private void applyRejectedAction(
            MissionTask mission,
            MissionRun run,
            ControlCommandStatusChangedEvent event
    ) {
        if (event.commandType() == CommandType.START_MISSION && run.getStatus() == MissionRunStatus.PENDING) {
            run.fail(run.getStage(), event.detail());
        }
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run.getId(),
                MissionEventType.ALERT,
                mission.getStage(),
                MissionEventLevel.ERROR,
                event.status() == CommandStatus.TIMEOUT ? "控制指令确认超时" : "控制指令执行失败",
                commandDescription(event),
                "command:" + event.commandKey()
        ));
    }

    private boolean activate(MissionTask mission, MissionRun run) {
        if (mission.getStatus() != MissionStatus.READY || run.getStatus() != MissionRunStatus.PENDING) return false;
        run.activate(run.getStage());
        mission.updateStatus(MissionStatus.RUNNING, run.getStage());
        return true;
    }

    private boolean pause(MissionTask mission, MissionRun run) {
        if (mission.getStatus() != MissionStatus.RUNNING || run.getStatus() != MissionRunStatus.RUNNING) return false;
        run.pause(mission.getStage());
        mission.updateStatus(MissionStatus.PAUSED, mission.getStage());
        return true;
    }

    private boolean resume(MissionTask mission, MissionRun run) {
        if (mission.getStatus() != MissionStatus.PAUSED || run.getStatus() != MissionRunStatus.PAUSED) return false;
        MissionStage stage = nextRunningStage(mission.getStage());
        run.resume(stage);
        mission.updateStatus(MissionStatus.RUNNING, stage);
        return true;
    }

    private boolean complete(MissionTask mission, MissionRun run) {
        if (!isActive(mission, run)) return false;
        run.complete(MissionStage.EVALUATION);
        mission.updateStatus(MissionStatus.COMPLETED, MissionStage.EVALUATION);
        return true;
    }

    private boolean fail(MissionTask mission, MissionRun run, String reason) {
        if (!isActive(mission, run)) return false;
        run.fail(mission.getStage(), reason == null ? "任务执行异常" : reason);
        mission.updateStatus(MissionStatus.FAILED, mission.getStage());
        return true;
    }

    private boolean cancel(MissionTask mission, MissionRun run) {
        if (mission.getStatus() == MissionStatus.READY && run.getStatus() == MissionRunStatus.PENDING) {
            run.cancel(MissionStage.EVALUATION);
            mission.updateStatus(MissionStatus.CANCELLED, MissionStage.EVALUATION);
            return true;
        }
        if (!isActive(mission, run)) return false;
        run.cancel(MissionStage.EVALUATION);
        mission.updateStatus(MissionStatus.CANCELLED, MissionStage.EVALUATION);
        return true;
    }

    private boolean isActive(MissionTask mission, MissionRun run) {
        return (mission.getStatus() == MissionStatus.RUNNING || mission.getStatus() == MissionStatus.PAUSED)
                && (run.getStatus() == MissionRunStatus.RUNNING || run.getStatus() == MissionRunStatus.PAUSED);
    }

    private MissionStage nextRunningStage(MissionStage stage) {
        if (stage == MissionStage.PREPARE) return MissionStage.TARGET_DETECTED;
        if (stage == MissionStage.EVALUATION) return MissionStage.TRACKING;
        return stage;
    }

    private boolean isMissionAction(CommandType commandType) {
        return commandType == CommandType.START_MISSION
                || commandType == CommandType.PAUSE_MISSION
                || commandType == CommandType.RESUME_MISSION
                || commandType == CommandType.COMPLETE_MISSION
                || commandType == CommandType.FAIL_MISSION
                || commandType == CommandType.CANCEL_MISSION;
    }

    private String commandDescription(ControlCommandStatusChangedEvent event) {
        String detail = event.detail() == null ? "无附加说明" : event.detail();
        return event.errorCode() == null
                ? event.commandType() + " / " + detail
                : event.commandType() + " / " + event.errorCode() + " / " + detail;
    }
}
