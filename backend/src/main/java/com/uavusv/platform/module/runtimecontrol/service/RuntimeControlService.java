package com.uavusv.platform.module.runtimecontrol.service;

import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandLogResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeControlResponse;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationSession;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import com.uavusv.platform.module.runtimecontrol.repository.ControlCommandRepository;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import org.springframework.beans.factory.annotation.Value;
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

    private final RuntimeStateService runtimeStateService;
    private final SimulationSessionRepository sessionRepository;
    private final ControlCommandRepository commandRepository;
    private final String wslDistribution;
    private final Path rosScript;
    private final Path unityEditor;
    private final Path unityProject;
    private final String rosWebSocketUrl;
    private final String integrationToken;

    public RuntimeControlService(
            RuntimeStateService runtimeStateService,
            SimulationSessionRepository sessionRepository,
            ControlCommandRepository commandRepository,
            @Value("${app.control.wsl-distribution}") String wslDistribution,
            @Value("${app.control.ros-script}") String rosScript,
            @Value("${app.control.unity-editor}") String unityEditor,
            @Value("${app.control.unity-project}") String unityProject,
            @Value("${app.runtime.ros-websocket-url}") String rosWebSocketUrl,
            @Value("${app.integration.token}") String integrationToken
    ) {
        this.runtimeStateService = runtimeStateService;
        this.sessionRepository = sessionRepository;
        this.commandRepository = commandRepository;
        this.wslDistribution = wslDistribution;
        this.rosScript = Path.of(rosScript);
        this.unityEditor = Path.of(unityEditor);
        this.unityProject = Path.of(unityProject);
        this.rosWebSocketUrl = rosWebSocketUrl;
        this.integrationToken = integrationToken;
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
    public List<RuntimeCommandLogResponse> recentCommands() {
        return commandRepository.findTop100ByOrderByRequestedAtDesc()
                .stream()
                .map(RuntimeCommandLogResponse::from)
                .toList();
    }

    @Transactional
    public RuntimeControlResponse start(String username) {
        var active = sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(ACTIVE_STATUSES);
        if (active.isPresent()) {
            ControlCommand command = commandRepository.save(new ControlCommand(active.get().getId(), CommandType.START, username));
            command.succeed("已有活动仿真会话，平台未重复启动");
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
        ControlCommand command = commandRepository.save(new ControlCommand(sessionId, request.commandType(), username));
        String detail = buildCommandDetail(request);
        command.succeed(detail);
        commandRepository.save(command);
        return new RuntimeCommandResponse(request.commandType(), CommandStatus.SUCCEEDED, detail, LocalDateTime.now());
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
}
