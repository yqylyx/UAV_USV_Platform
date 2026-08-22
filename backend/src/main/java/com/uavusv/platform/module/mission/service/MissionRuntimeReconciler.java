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
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;
import java.util.Optional;

@Service
public class MissionRuntimeReconciler {

    private static final Logger log = LoggerFactory.getLogger(MissionRuntimeReconciler.class);
    private static final EnumSet<MissionRunStatus> OPEN_RUN_STATUSES = EnumSet.of(
            MissionRunStatus.PENDING,
            MissionRunStatus.RUNNING,
            MissionRunStatus.PAUSED
    );

    private final MissionRunRepository missionRunRepository;
    private final MissionTaskRepository missionTaskRepository;
    private final MissionEventRepository missionEventRepository;
    private final ControlCommandRepository controlCommandRepository;

    public MissionRuntimeReconciler(
            MissionRunRepository missionRunRepository,
            MissionTaskRepository missionTaskRepository,
            MissionEventRepository missionEventRepository,
            ControlCommandRepository controlCommandRepository
    ) {
        this.missionRunRepository = missionRunRepository;
        this.missionTaskRepository = missionTaskRepository;
        this.missionEventRepository = missionEventRepository;
        this.controlCommandRepository = controlCommandRepository;
    }

    @Transactional
    public void reconcileCommandStatus(ControlCommandStatusChangedEvent event) {
        if (event.runId() == null || !isMissionAction(event.commandType())) {
            return;
        }
        MissionRun run = missionRunRepository.findById(event.runId()).orElse(null);
        if (run == null) {
            log.warn("Mission command reconciliation skipped: runId={} does not exist", event.runId());
            return;
        }
        MissionTask mission = missionTaskRepository.findById(run.getMissionId()).orElse(null);
        if (!validMission(mission, run, "command:" + event.commandKey())) {
            return;
        }

        if (event.commandType() == CommandType.START_MISSION && event.status() == CommandStatus.EXECUTING) {
            reconcileRunning(mission, run, "START_MISSION EXECUTING", "command:" + event.commandKey());
            return;
        }
        if (event.status() == CommandStatus.SUCCEEDED) {
            reconcileSucceededCommand(mission, run, event);
        } else if (event.commandType() == CommandType.CANCEL_MISSION && event.status() == CommandStatus.CANCELLED) {
            reconcileTerminal(mission, run, MissionRunStatus.CANCELLED, MissionStatus.CANCELLED,
                    MissionStage.EVALUATION, null, commandDescription(event), "command:" + event.commandKey());
        } else if (event.status() == CommandStatus.FAILED || event.status() == CommandStatus.TIMEOUT
                || event.status() == CommandStatus.CANCELLED || event.status() == CommandStatus.REJECTED) {
            reconcileRejectedCommand(mission, run, event);
        }
    }

    @Transactional
    public void reconcileMissionStatus(
            String missionIdValue,
            String envelopeRunId,
            String payloadRunId,
            String activeCommandId,
            String state,
            String phase,
            String source
    ) {
        RuntimeFact fact = normalizeMissionStatus(state);
        if (fact == RuntimeFact.UNKNOWN) {
            return;
        }
        ResolvedScope scope = resolveScope(missionIdValue, firstText(payloadRunId, envelopeRunId), activeCommandId, source);
        if (scope == null) {
            return;
        }
        MissionRun run = missionRunRepository.findById(scope.runId()).orElse(null);
        if (run == null) {
            log.warn("Mission status reconciliation skipped: runId={} does not exist source={}", scope.runId(), source);
            return;
        }
        if (scope.missionId() != null && !scope.missionId().equals(run.getMissionId())) {
            log.warn("Mission status reconciliation skipped: missionId={} does not match runId={} missionId={} source={}",
                    scope.missionId(), run.getId(), run.getMissionId(), source);
            return;
        }
        MissionTask mission = missionTaskRepository.findById(run.getMissionId()).orElse(null);
        if (!validMission(mission, run, source)) {
            return;
        }

        String detail = "state=" + normalizeText(state) + optionalDetail("phase", phase)
                + optionalDetail("activeCommandId", activeCommandId);
        switch (fact) {
            case COMPLETED -> reconcileTerminal(mission, run, MissionRunStatus.COMPLETED, MissionStatus.COMPLETED,
                    MissionStage.EVALUATION, null, detail, source);
            case CANCELLED -> reconcileTerminal(mission, run, MissionRunStatus.CANCELLED, MissionStatus.CANCELLED,
                    MissionStage.EVALUATION, null, detail, source);
            case FAILED -> reconcileTerminal(mission, run, MissionRunStatus.FAILED, MissionStatus.FAILED,
                    mission.getStage(), detail, detail, source);
            default -> { }
        }
    }

    RuntimeFact normalizeMissionStatus(String state) {
        return switch (normalizeText(state)) {
            case "SUCCESS", "SUCCEEDED", "COMPLETED" -> RuntimeFact.COMPLETED;
            case "CANCELLED", "CANCELED" -> RuntimeFact.CANCELLED;
            case "FAILED" -> RuntimeFact.FAILED;
            default -> RuntimeFact.UNKNOWN;
        };
    }

    private ResolvedScope resolveScope(String missionIdValue, String runIdValue, String activeCommandId, String source) {
        Long missionId = parseLongOrNull(missionIdValue, "missionId", source);
        Long runId = parseLongOrNull(runIdValue, "runId", source);
        if (runId != null) {
            return new ResolvedScope(missionId, runId);
        }
        String commandKey = firstText(activeCommandId, null);
        if (commandKey != null) {
            Optional<ControlCommand> command = controlCommandRepository.findByCommandKey(commandKey);
            if (command.isPresent() && command.get().getRunId() != null) {
                return new ResolvedScope(missionId, command.get().getRunId());
            }
            log.warn("Mission status reconciliation skipped: activeCommandId={} cannot resolve a runId source={}",
                    commandKey, source);
            return null;
        }
        log.warn("Mission status reconciliation skipped: runId is not explicit and no command scope is available missionId={} source={}",
                missionIdValue, source);
        return null;
    }

    private void reconcileSucceededCommand(
            MissionTask mission,
            MissionRun run,
            ControlCommandStatusChangedEvent event
    ) {
        switch (event.commandType()) {
            case START_MISSION -> reconcileRunning(mission, run, "START_MISSION SUCCEEDED", "command:" + event.commandKey());
            case PAUSE_MISSION -> reconcilePause(mission, run, event);
            case RESUME_MISSION -> reconcileResume(mission, run, event);
            case COMPLETE_MISSION -> reconcileTerminal(mission, run, MissionRunStatus.COMPLETED, MissionStatus.COMPLETED,
                    MissionStage.EVALUATION, null, commandDescription(event), "command:" + event.commandKey());
            case FAIL_MISSION -> reconcileTerminal(mission, run, MissionRunStatus.FAILED, MissionStatus.FAILED,
                    mission.getStage(), event.detail(), commandDescription(event), "command:" + event.commandKey());
            case CANCEL_MISSION -> reconcileTerminal(mission, run, MissionRunStatus.CANCELLED, MissionStatus.CANCELLED,
                    MissionStage.EVALUATION, null, commandDescription(event), "command:" + event.commandKey());
            default -> { }
        }
    }

    private void reconcileRejectedCommand(
            MissionTask mission,
            MissionRun run,
            ControlCommandStatusChangedEvent event
    ) {
        boolean changed = false;
        if (event.commandType() == CommandType.START_MISSION && run.getStatus() == MissionRunStatus.PENDING) {
            run.fail(run.getStage(), event.detail());
            changed = true;
        }
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run.getId(),
                MissionEventType.ALERT,
                mission.getStage(),
                MissionEventLevel.ERROR,
                event.status() == CommandStatus.TIMEOUT ? "Mission command timed out" : "Mission command failed",
                commandDescription(event),
                "command:" + event.commandKey()
        ));
        if (changed) {
            log.info("Mission command rejected: runId={} commandKey={} status={}", run.getId(), event.commandKey(), event.status());
        }
    }

    private void reconcileRunning(MissionTask mission, MissionRun run, String detail, String source) {
        if (isTerminal(run.getStatus()) || isTerminal(mission.getStatus())) {
            return;
        }
        if (mission.getStatus() == MissionStatus.RUNNING && run.getStatus() == MissionRunStatus.RUNNING) {
            return;
        }
        if (mission.getStatus() != MissionStatus.READY || run.getStatus() != MissionRunStatus.PENDING) {
            recordNoChange(mission, run, detail, source);
            return;
        }
        run.activate(run.getStage());
        mission.updateStatus(MissionStatus.RUNNING, run.getStage());
        recordStatus(mission, run, MissionEventLevel.INFO, "Mission runtime reconciled to RUNNING", detail, source);
    }

    private void reconcilePause(MissionTask mission, MissionRun run, ControlCommandStatusChangedEvent event) {
        if (isTerminal(run.getStatus()) || isTerminal(mission.getStatus())) {
            return;
        }
        if (mission.getStatus() == MissionStatus.PAUSED && run.getStatus() == MissionRunStatus.PAUSED) {
            return;
        }
        if (mission.getStatus() != MissionStatus.RUNNING || run.getStatus() != MissionRunStatus.RUNNING) {
            recordNoChange(mission, run, commandDescription(event), "command:" + event.commandKey());
            return;
        }
        run.pause(mission.getStage());
        mission.updateStatus(MissionStatus.PAUSED, mission.getStage());
        recordStatus(mission, run, MissionEventLevel.INFO, "Mission runtime reconciled to PAUSED",
                commandDescription(event), "command:" + event.commandKey());
    }

    private void reconcileResume(MissionTask mission, MissionRun run, ControlCommandStatusChangedEvent event) {
        if (isTerminal(run.getStatus()) || isTerminal(mission.getStatus())) {
            return;
        }
        if (mission.getStatus() == MissionStatus.RUNNING && run.getStatus() == MissionRunStatus.RUNNING) {
            return;
        }
        if (mission.getStatus() != MissionStatus.PAUSED || run.getStatus() != MissionRunStatus.PAUSED) {
            recordNoChange(mission, run, commandDescription(event), "command:" + event.commandKey());
            return;
        }
        MissionStage stage = nextRunningStage(mission.getStage());
        run.resume(stage);
        mission.updateStatus(MissionStatus.RUNNING, stage);
        recordStatus(mission, run, MissionEventLevel.INFO, "Mission runtime reconciled to RUNNING",
                commandDescription(event), "command:" + event.commandKey());
    }

    private void reconcileTerminal(
            MissionTask mission,
            MissionRun run,
            MissionRunStatus runStatus,
            MissionStatus missionStatus,
            MissionStage stage,
            String failureReason,
            String detail,
            String source
    ) {
        if (isTerminal(run.getStatus())) {
            return;
        }
        MissionStatus previousMissionStatus = mission.getStatus();
        MissionRunStatus previousRunStatus = run.getStatus();
        applyRunTerminal(run, runStatus, stage, failureReason);
        Optional<MissionRun> openRun = missionRunRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(
                mission.getId(), OPEN_RUN_STATUSES);
        boolean targetRunIsCurrentOpenRun = openRun.map(MissionRun::getId).map(id -> id.equals(run.getId())).orElse(true);
        if (targetRunIsCurrentOpenRun
                && shouldUpdateMissionForTerminal(previousMissionStatus, previousRunStatus, runStatus)) {
            mission.updateStatus(missionStatus, stage);
        }
        recordStatus(mission, run, runStatus == MissionRunStatus.FAILED ? MissionEventLevel.ERROR : MissionEventLevel.INFO,
                "Mission runtime reconciled to " + runStatus.name(), detail, source);
    }

    private void applyRunTerminal(MissionRun run, MissionRunStatus status, MissionStage stage, String failureReason) {
        switch (status) {
            case COMPLETED -> run.complete(stage);
            case CANCELLED -> run.cancel(stage);
            case FAILED -> run.fail(stage, failureReason == null ? "Mission runtime reported FAILED" : failureReason);
            default -> throw new IllegalArgumentException("Unsupported terminal run status: " + status);
        }
    }

    private boolean validMission(MissionTask mission, MissionRun run, String source) {
        if (mission == null || mission.isDeleted()) {
            log.warn("Mission runtime reconciliation skipped: missionId={} is missing or deleted source={}",
                    run.getMissionId(), source);
            return false;
        }
        return true;
    }

    private void recordStatus(
            MissionTask mission,
            MissionRun run,
            MissionEventLevel level,
            String title,
            String detail,
            String source
    ) {
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run.getId(),
                MissionEventType.STATUS,
                mission.getStage(),
                level,
                title,
                detail,
                source
        ));
    }

    private void recordNoChange(MissionTask mission, MissionRun run, String detail, String source) {
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run.getId(),
                MissionEventType.ALERT,
                mission.getStage(),
                MissionEventLevel.WARNING,
                "Mission runtime reconciliation made no state change",
                detail,
                source
        ));
    }

    private boolean isMissionAction(CommandType commandType) {
        return commandType == CommandType.START_MISSION
                || commandType == CommandType.PAUSE_MISSION
                || commandType == CommandType.RESUME_MISSION
                || commandType == CommandType.COMPLETE_MISSION
                || commandType == CommandType.FAIL_MISSION
                || commandType == CommandType.CANCEL_MISSION;
    }

    private boolean isTerminal(MissionRunStatus status) {
        return status == MissionRunStatus.COMPLETED
                || status == MissionRunStatus.CANCELLED
                || status == MissionRunStatus.FAILED;
    }

    private boolean isTerminal(MissionStatus status) {
        return status == MissionStatus.COMPLETED
                || status == MissionStatus.CANCELLED
                || status == MissionStatus.FAILED;
    }

    private boolean shouldUpdateMissionForTerminal(
            MissionStatus missionStatus,
            MissionRunStatus runStatus,
            MissionRunStatus targetRunStatus
    ) {
        if (isTerminal(missionStatus)) {
            return false;
        }
        if (missionStatus == MissionStatus.RUNNING || missionStatus == MissionStatus.PAUSED) {
            return runStatus == MissionRunStatus.RUNNING || runStatus == MissionRunStatus.PAUSED;
        }
        return missionStatus == MissionStatus.READY
                && runStatus == MissionRunStatus.PENDING
                && targetRunStatus == MissionRunStatus.CANCELLED;
    }

    private MissionStage nextRunningStage(MissionStage stage) {
        if (stage == MissionStage.PREPARE) return MissionStage.TARGET_DETECTED;
        if (stage == MissionStage.EVALUATION) return MissionStage.TRACKING;
        return stage;
    }

    private String commandDescription(ControlCommandStatusChangedEvent event) {
        String detail = event.detail() == null ? "no detail" : event.detail();
        return event.errorCode() == null
                ? event.commandType() + " / " + event.status() + " / " + detail
                : event.commandType() + " / " + event.status() + " / " + event.errorCode() + " / " + detail;
    }

    private String optionalDetail(String key, String value) {
        String text = firstText(value, null);
        return text == null ? "" : " " + key + "=" + text;
    }

    private String normalizeText(String value) {
        return value == null ? "" : value.trim().toUpperCase().replace('-', '_').replace(' ', '_');
    }

    private String firstText(String first, String second) {
        if (first != null && !first.isBlank()) {
            return first.trim();
        }
        if (second != null && !second.isBlank()) {
            return second.trim();
        }
        return null;
    }

    private Long parseLongOrNull(String value, String fieldName, String source) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Long.valueOf(value.trim());
        } catch (NumberFormatException exception) {
            log.warn("Mission runtime reconciliation skipped: {}={} is not a numeric id source={}",
                    fieldName, value, source);
            return null;
        }
    }

    enum RuntimeFact {
        COMPLETED,
        CANCELLED,
        FAILED,
        UNKNOWN
    }

    private record ResolvedScope(Long missionId, Long runId) {
    }
}
