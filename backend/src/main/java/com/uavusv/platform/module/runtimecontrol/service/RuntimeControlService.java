package com.uavusv.platform.module.runtimecontrol.service;

import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dispatch.CommandDispatchResult;
import com.uavusv.platform.module.runtimecontrol.dispatch.RuntimeCommandDispatcher;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandAckRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandLogResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeControlResponse;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationSession;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.EnumSet;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
public class RuntimeControlService {

    private static final EnumSet<SimulationStatus> ACTIVE_STATUSES = EnumSet.of(
            SimulationStatus.STARTING, SimulationStatus.RUNNING,
            SimulationStatus.PARTIAL, SimulationStatus.STOPPING
    );
    private static final EnumSet<CommandType> UAV_COMMANDS = EnumSet.of(
            CommandType.TAKEOFF,
            CommandType.LAND,
            CommandType.UAV_TAKEOFF,
            CommandType.UAV_HOVER,
            CommandType.UAV_RESUME,
            CommandType.UAV_RETURN,
            CommandType.UAV_LAND,
            CommandType.UAV_EMERGENCY_LAND
    );
    private static final EnumSet<CommandType> USV_COMMANDS = EnumSet.of(
            CommandType.USV_DEPART,
            CommandType.USV_HOLD,
            CommandType.USV_RESUME,
            CommandType.USV_RETURN,
            CommandType.USV_STOP,
            CommandType.USV_EMERGENCY_STOP
    );

    private final RuntimeStateService runtimeStateService;
    private final SimulationSessionRepository sessionRepository;
    private final ControlCommandRepository commandRepository;
    private final DeviceRepository deviceRepository;
    private final MissionRunRepository missionRunRepository;
    private final RuntimeCommandDispatcher commandDispatcher;
    private final ApplicationEventPublisher eventPublisher;
    private final String wslDistribution;
    private final Path rosScript;
    private final Path unityEditor;
    private final Path unityProject;
    private final String rosWebSocketUrl;
    private final String integrationToken;
    private final String commandDispatchMode;
    private final long commandAckTimeoutSeconds;

    public RuntimeControlService(
            RuntimeStateService runtimeStateService,
            SimulationSessionRepository sessionRepository,
            ControlCommandRepository commandRepository,
            DeviceRepository deviceRepository,
            MissionRunRepository missionRunRepository,
            RuntimeCommandDispatcher commandDispatcher,
            ApplicationEventPublisher eventPublisher,
            @Value("${app.control.wsl-distribution}") String wslDistribution,
            @Value("${app.control.ros-script}") String rosScript,
            @Value("${app.control.unity-editor}") String unityEditor,
            @Value("${app.control.unity-project}") String unityProject,
            @Value("${app.runtime.ros-websocket-url}") String rosWebSocketUrl,
            @Value("${app.integration.token}") String integrationToken,
            @Value("${app.control.command-dispatch-mode:browser-unity}") String commandDispatchMode,
            @Value("${app.control.command-ack-timeout-seconds:15}") long commandAckTimeoutSeconds
    ) {
        this.runtimeStateService = runtimeStateService;
        this.sessionRepository = sessionRepository;
        this.commandRepository = commandRepository;
        this.deviceRepository = deviceRepository;
        this.missionRunRepository = missionRunRepository;
        this.commandDispatcher = commandDispatcher;
        this.eventPublisher = eventPublisher;
        this.wslDistribution = wslDistribution;
        this.rosScript = Path.of(rosScript);
        this.unityEditor = Path.of(unityEditor);
        this.unityProject = Path.of(unityProject);
        this.rosWebSocketUrl = rosWebSocketUrl;
        this.integrationToken = integrationToken;
        this.commandDispatchMode = commandDispatchMode;
        this.commandAckTimeoutSeconds = Math.max(commandAckTimeoutSeconds, 1);
    }

    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void resetRuntimeStateOnApplicationReady() {
        sessionRepository.findAll().stream()
                .filter(session -> ACTIVE_STATUSES.contains(session.getStatus()))
                .forEach(session -> session.updateStatus(SimulationStatus.STOPPED));
        runtimeStateService.markRuntimeStopped("平台服务已启动，等待手动点击运行");
    }

    @Transactional(readOnly = true)
    public RuntimeControlResponse getStatus() {
        boolean rosOnline = runtimeStateService.isOnline(RuntimeStateService.ROS_CODE);
        boolean unityOnline = runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE);
        return sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(ACTIVE_STATUSES)
                .map(session -> RuntimeControlResponse.from(session, rosOnline, unityOnline, statusMessage(session, rosOnline, unityOnline)))
                .orElseGet(() -> new RuntimeControlResponse(
                        null,
                        SimulationStatus.STOPPED,
                        false,
                        false,
                        false,
                        false,
                        false,
                        null,
                        "仿真未运行"
                ));
    }

    @Transactional(readOnly = true)
    public List<RuntimeCommandLogResponse> recentCommands(Long runId, int limit) {
        var pageable = org.springframework.data.domain.PageRequest.of(0, Math.min(Math.max(limit, 1), 100));
        var commands = runId == null
                ? commandRepository.findAllByOrderByRequestedAtDesc(pageable)
                : commandRepository.findByRunIdOrderByRequestedAtDesc(runId, pageable);
        return commands
                .stream()
                .map(RuntimeCommandLogResponse::from)
                .toList();
    }

    @Transactional
    public RuntimeControlResponse start(String username) {
        var active = sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(ACTIVE_STATUSES);
        if (active.isPresent()) {
            SimulationSession session = active.get();
            ControlCommand command = commandRepository.save(new ControlCommand(session.getId(), CommandType.START, username));
            boolean rosOnline = runtimeStateService.isOnline(RuntimeStateService.ROS_CODE);
            boolean unityOnline = runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE);
            boolean retried = false;
            try {
                if (!rosOnline) {
                    runRosScript("start");
                    retried = true;
                }
                if (!unityOnline) {
                    requestUnityStart();
                    retried = true;
                }
                command.succeed(retried ? "已有活动仿真会话，已补启动离线组件" : "已有活动仿真会话，平台未重复启动");
                session.updateStatus(statusFromHeartbeats(
                        runtimeStateService.isOnline(RuntimeStateService.ROS_CODE),
                        runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE)
                ));
                sessionRepository.save(session);
            } catch (Exception exception) {
                command.fail(exception.getMessage());
                session.fail(exception.getMessage());
                sessionRepository.save(session);
            }
            commandRepository.save(command);
            return getStatus();
        }

        boolean rosAlreadyOnline = runtimeStateService.isOnline(RuntimeStateService.ROS_CODE);
        boolean unityAlreadyOnline = runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE);
        SimulationSession session = sessionRepository.save(new SimulationSession(UUID.randomUUID().toString(), username));
        ControlCommand command = commandRepository.save(new ControlCommand(session.getId(), CommandType.START, username));

        boolean rosManaged = false;
        boolean unityManaged = false;
        Long unityProcessId = null;
        try {
            if (!rosAlreadyOnline) {
                runRosScript("start");
                rosManaged = true;
            }
            if (!unityAlreadyOnline) {
                unityProcessId = requestUnityStart();
                unityManaged = true;
            }

            session.configureOwnership(rosManaged, unityManaged, null, unityProcessId);
            if (rosAlreadyOnline && unityAlreadyOnline) {
                session.updateStatus(SimulationStatus.RUNNING);
                command.succeed("ROS 和 Unity 已在外部运行，平台已接入监控且不会重复启动");
            } else {
                session.updateStatus((rosAlreadyOnline || unityAlreadyOnline) ? SimulationStatus.PARTIAL : SimulationStatus.STARTING);
                command.succeed("启动指令已提交，等待真实心跳确认");
            }
        } catch (Exception exception) {
            session.fail(exception.getMessage());
            command.fail(exception.getMessage());
        }

        sessionRepository.save(session);
        commandRepository.save(command);
        return RuntimeControlResponse.from(session,
                runtimeStateService.isOnline(RuntimeStateService.ROS_CODE),
                runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE),
                session.getErrorMessage() == null ? "启动状态由真实心跳确认" : session.getErrorMessage());
    }

    @Transactional
    public RuntimeControlResponse stop(String username) {
        var active = sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(ACTIVE_STATUSES);
        if (active.isEmpty()) {
            ControlCommand command = commandRepository.save(new ControlCommand(null, CommandType.STOP, username));
            try {
                runRosScript("stop");
                requestUnityStop();
                runtimeStateService.markRuntimeStopped("平台停止指令已执行，运行节点已下线");
                command.succeed("未找到活动会话，已执行停止清理并下线运行节点");
                commandRepository.save(command);
                return new RuntimeControlResponse(
                        null,
                        SimulationStatus.STOPPED,
                        false,
                        false,
                        false,
                        false,
                        false,
                        null,
                        "未找到活动会话，已执行停止清理并下线运行节点"
                );
            } catch (Exception exception) {
                command.fail(exception.getMessage());
                commandRepository.save(command);
                return new RuntimeControlResponse(
                        null,
                        SimulationStatus.FAILED,
                        runtimeStateService.isOnline(RuntimeStateService.ROS_CODE),
                        runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE),
                        false,
                        false,
                        true,
                        null,
                        exception.getMessage()
                );
            }
        }

        SimulationSession session = active.get();
        ControlCommand command = commandRepository.save(new ControlCommand(session.getId(), CommandType.STOP, username));
        session.updateStatus(SimulationStatus.STOPPING);
        try {
            requestUnityStop();
            runRosScript("stop");
            runtimeStateService.markRuntimeStopped("平台停止指令已执行，运行节点已下线");
            session.updateStatus(SimulationStatus.STOPPED);
            command.succeed("已执行平台停止指令，ROS/Gazebo 与 Unity 联动节点已下线");
        } catch (Exception exception) {
            session.fail(exception.getMessage());
            command.fail(exception.getMessage());
        }
        sessionRepository.save(session);
        commandRepository.save(command);
        return RuntimeControlResponse.from(session,
                runtimeStateService.isOnline(RuntimeStateService.ROS_CODE),
                runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE),
                session.getErrorMessage() == null ? "停止指令已完成" : session.getErrorMessage());
    }

    @Transactional
    public RuntimeCommandResponse issueCommand(RuntimeCommandRequest request, String username) {
        Long sessionId = sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(ACTIVE_STATUSES)
                .map(SimulationSession::getId)
                .orElse(null);
        Device targetDevice = resolveDevice(request.deviceCode());
        validateCommandTarget(request.commandType(), targetDevice);
        Long deviceId = targetDevice == null ? null : targetDevice.getId();
        validateRun(request.runId());
        RuntimeScope runtimeScope = request.runtimeScope() != null
                ? request.runtimeScope()
                : (request.runId() == null ? RuntimeScope.SYSTEM_OVERVIEW : RuntimeScope.MISSION_CENTER);
        if (request.runId() != null && runtimeScope != RuntimeScope.MISSION_CENTER) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "任务执行批次只能向任务中心运行实例下发指令");
        }
        ensureNoPendingCommand(request.runId(), deviceId);
        ControlCommand command = commandRepository.save(new ControlCommand(
                sessionId,
                request.runId(),
                deviceId,
                request.commandType(),
                request.payload(),
                username,
                runtimeScope,
                request.runtimeInstanceId()
        ));
        command.dispatch(buildCommandDetail(request));
        commandRepository.save(command);

        try {
            CommandDispatchResult dispatchResult = commandDispatcher.dispatch(command.getCommandKey(), request);
            if (!dispatchResult.accepted()) {
                command.fail(dispatchResult.errorCode(), dispatchResult.detail());
            } else if (dispatchResult.acknowledged()) {
                command.acknowledge(dispatchResult.detail());
            } else if (dispatchResult.detail() != null && !dispatchResult.detail().isBlank()) {
                command.dispatch(dispatchResult.detail());
            }
        } catch (Exception exception) {
            command.fail("DISPATCH_EXCEPTION", exception.getMessage());
        }
        commandRepository.save(command);
        publishTerminalCommandStatus(command);
        return RuntimeCommandResponse.from(command);
    }

    @Transactional
    public RuntimeCommandResponse acknowledgeCommand(String commandKey, RuntimeCommandAckRequest request) {
        ControlCommand command = commandRepository.findByCommandKey(commandKey)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "控制指令不存在"));
        if ("ros-websocket".equalsIgnoreCase(commandDispatchMode)
                && "UNITY_WEBGL".equalsIgnoreCase(request.source())) {
            return RuntimeCommandResponse.from(command);
        }
        if (command.getStatus() == CommandStatus.ACKNOWLEDGED
                || command.getStatus() == CommandStatus.FAILED
                || command.getStatus() == CommandStatus.TIMEOUT) {
            return RuntimeCommandResponse.from(command);
        }
        if (Boolean.TRUE.equals(request.success())) {
            command.acknowledge(request.detail() == null ? "外部组件已确认执行" : request.detail());
        } else {
            command.fail(
                    request.errorCode() == null ? "REMOTE_EXECUTION_FAILED" : request.errorCode(),
                    request.detail() == null ? "外部组件执行失败" : request.detail()
            );
        }
        commandRepository.save(command);
        publishTerminalCommandStatus(command);
        return RuntimeCommandResponse.from(command);
    }

    @Scheduled(fixedDelay = 5000)
    @Transactional
    public void expireUnacknowledgedCommands() {
        LocalDateTime cutoff = LocalDateTime.now().minusSeconds(commandAckTimeoutSeconds);
        commandRepository.findAllByStatusAndDispatchedAtBefore(CommandStatus.DISPATCHED, cutoff)
                .forEach(command -> {
                    command.timeout("指令下发后未在规定时间内收到确认");
                    commandRepository.save(command);
                    publishTerminalCommandStatus(command);
                });
    }

    @Scheduled(fixedDelay = 2000)
    @Transactional
    public void reconcileSession() {
        sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(
                        EnumSet.of(SimulationStatus.STARTING, SimulationStatus.RUNNING, SimulationStatus.PARTIAL))
                .ifPresent(session -> {
                    boolean rosOnline = runtimeStateService.isOnline(RuntimeStateService.ROS_CODE);
                    boolean unityOnline = runtimeStateService.isOnline(RuntimeStateService.UNITY_CODE);
                    if (rosOnline && unityOnline) {
                        session.updateStatus(SimulationStatus.RUNNING);
                    } else if (rosOnline || unityOnline) {
                        session.updateStatus(SimulationStatus.PARTIAL);
                    } else if (Duration.between(session.getStartedAt(), java.time.LocalDateTime.now()).toSeconds() > 45) {
                        session.fail("启动超时：45 秒内未收到 ROS 或 Unity 心跳");
                    } else {
                        session.updateStatus(SimulationStatus.STARTING);
                    }
                });
    }

    private String runRosScript(String action) throws IOException, InterruptedException {
        if (!Files.isRegularFile(rosScript)) {
            throw new IOException("ROS 启动脚本不存在: " + rosScript);
        }
        String linuxScript = toWslPath(rosScript);
        Process process = new ProcessBuilder("wsl.exe", "-d", wslDistribution, "--", "bash", linuxScript, action)
                .redirectErrorStream(true)
                .start();
        boolean finished = process.waitFor(20, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IOException("ROS " + action + " 命令执行超时");
        }
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        if (process.exitValue() != 0) {
            throw new IOException("ROS " + action + " 失败: " + output);
        }
        return output;
    }

    private Long requestUnityStart() throws IOException {
        Path controlDirectory = unityProject.resolve("Library").resolve("PlatformControl");
        Files.createDirectories(controlDirectory);
        Files.deleteIfExists(controlDirectory.resolve("stop.request"));
        Files.writeString(controlDirectory.resolve("start.request"), "start", StandardCharsets.UTF_8);

        if (isUnityProjectOpen()) {
            return null;
        }
        if (!Files.isRegularFile(unityEditor)) {
            throw new IOException("Unity Editor 不存在: " + unityEditor);
        }
        Process process = new ProcessBuilder(
                unityEditor.toString(),
                "-projectPath", unityProject.toString(),
                "--platform-auto-play",
                "--platform-exit-on-stop",
                "--ros-ws",
                "--ros-ws-url=" + rosWebSocketUrl,
                "--platform-url=http://127.0.0.1:8081/api/integration/heartbeat",
                "--platform-token=" + integrationToken
        ).start();
        return process.pid();
    }

private void requestUnityStop() throws IOException {
    Path controlDirectory = unityProject.resolve("Library").resolve("PlatformControl");
    Files.createDirectories(controlDirectory);

    // 停止时删除启动请求，防止 Unity 或监听逻辑再次读取 start.request 后重新启动
    Files.deleteIfExists(controlDirectory.resolve("start.request"));

    // 写入停止请求
    Files.writeString(controlDirectory.resolve("stop.request"), "stop", StandardCharsets.UTF_8);
}

    private String buildCommandDetail(RuntimeCommandRequest request) {
        StringBuilder detail = new StringBuilder("Web 控制台指令已记录");
        if (request.deviceCode() != null && !request.deviceCode().isBlank()) {
            detail.append("，目标设备=").append(request.deviceCode());
        }
        if (request.detail() != null && !request.detail().isBlank()) {
            detail.append("，说明=").append(request.detail());
        }
        if (request.payload() != null && !request.payload().isBlank()) {
            detail.append("，载荷=").append(request.payload());
        }
        return detail.toString();
    }

    private Device resolveDevice(String deviceCode) {
        if (deviceCode == null || deviceCode.isBlank()) {
            return null;
        }
        return deviceRepository.findByCode(deviceCode)
                .filter(device -> !device.isDeleted())
                .orElseThrow(() -> new BusinessException(ErrorCode.DEVICE_NOT_FOUND));
    }

    private void validateCommandTarget(CommandType commandType, Device targetDevice) {
        boolean uavCommand = UAV_COMMANDS.contains(commandType);
        boolean usvCommand = USV_COMMANDS.contains(commandType);
        if (!uavCommand && !usvCommand) {
            return;
        }
        if (targetDevice == null) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "载具控制指令必须指定目标设备");
        }
        if (uavCommand && targetDevice.getType() != DeviceType.UAV) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "无人机指令不能下发给非 UAV 设备");
        }
        if (usvCommand && targetDevice.getType() != DeviceType.USV) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "无人艇指令不能下发给非 USV 设备");
        }
    }

    private void validateRun(Long runId) {
        if (runId != null && !missionRunRepository.existsById(runId)) {
            throw new BusinessException(ErrorCode.NOT_FOUND, "任务执行记录不存在");
        }
    }

    private void ensureNoPendingCommand(Long runId, Long deviceId) {
        if (runId == null) return;
        EnumSet<CommandStatus> pendingStatuses = EnumSet.of(CommandStatus.PENDING, CommandStatus.DISPATCHED);
        boolean duplicated = deviceId == null
                ? commandRepository.existsByRunIdAndDeviceIdIsNullAndStatusIn(runId, pendingStatuses)
                : commandRepository.existsByRunIdAndDeviceIdAndStatusIn(runId, deviceId, pendingStatuses);
        if (duplicated) {
            throw new BusinessException(
                    ErrorCode.BAD_REQUEST,
                    deviceId == null ? "当前任务批次已有等待确认的任务指令" : "目标设备已有等待确认的控制指令"
            );
        }
    }

    private void publishTerminalCommandStatus(ControlCommand command) {
        if (command.getStatus() != CommandStatus.ACKNOWLEDGED
                && command.getStatus() != CommandStatus.FAILED
                && command.getStatus() != CommandStatus.TIMEOUT) {
            return;
        }
        eventPublisher.publishEvent(new ControlCommandStatusChangedEvent(
                command.getId(),
                command.getCommandKey(),
                command.getRunId(),
                command.getCommandType(),
                command.getStatus(),
                command.getDetail(),
                command.getErrorCode()
        ));
    }

    private boolean isUnityProjectOpen() {
        String expected = unityProject.toAbsolutePath().toString().toLowerCase();
        return ProcessHandle.allProcesses()
                .map(ProcessHandle::info)
                .map(ProcessHandle.Info::commandLine)
                .flatMap(java.util.Optional::stream)
                .map(String::toLowerCase)
                .anyMatch(command -> command.contains("unity.exe") && command.contains(expected));
    }

    private String toWslPath(Path windowsPath) {
        String value = windowsPath.toAbsolutePath().toString().replace('\\', '/');
        if (value.length() > 2 && value.charAt(1) == ':') {
            return "/mnt/" + Character.toLowerCase(value.charAt(0)) + value.substring(2);
        }
        return value;
    }

    private String statusMessage(SimulationSession session, boolean rosOnline, boolean unityOnline) {
        if (session.getErrorMessage() != null) {
            return session.getErrorMessage();
        }
        if (!session.isRosManaged() && !session.isUnityManaged()) {
            return "检测到外部运行实例，平台仅监控";
        }
        if (rosOnline && unityOnline) {
            return "ROS、Unity 及设备状态正常";
        }
        return "正在等待组件心跳";
    }

    private SimulationStatus statusFromHeartbeats(boolean rosOnline, boolean unityOnline) {
        if (rosOnline && unityOnline) {
            return SimulationStatus.RUNNING;
        }
        if (rosOnline || unityOnline) {
            return SimulationStatus.PARTIAL;
        }
        return SimulationStatus.STARTING;
    }
}
