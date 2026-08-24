package com.uavusv.platform.module.monitoring.service;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.monitoring.dto.request.IntegrationHeartbeatRequest;
import com.uavusv.platform.module.monitoring.dto.request.RosPoseFrame;
import com.uavusv.platform.module.monitoring.entity.DeviceStatusEvent;
import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.entity.RuntimePose;
import com.uavusv.platform.module.monitoring.repository.DeviceStatusEventRepository;
import com.uavusv.platform.module.monitoring.repository.DeviceTelemetryRepository;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.uavusv.platform.module.gateway.v1.DeviceCodeMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.net.URI;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.EnumSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Service
public class RuntimeStateService {

    public static final String UAV_CODE = "uav-01";
    public static final String USV_CODE = "usv-01";
    public static final String ROS_CODE = "ros-bridge-01";
    public static final String UNITY_CODE = "unity-client-01";

    private static final String ROS_POSE_DETAIL_PREFIX = "Gazebo pose sequence ";
    private static final EnumSet<DeviceType> RUNTIME_TYPES = EnumSet.of(
            DeviceType.UAV, DeviceType.USV, DeviceType.ROS_NODE, DeviceType.UNITY_NODE
    );

    private final DeviceRepository deviceRepository;
    private final RuntimeDeviceStatusRepository runtimeStatusRepository;
    private final DeviceStatusEventRepository statusEventRepository;
    private final DeviceTelemetryRepository telemetryRepository;
    private final RuntimeEventPublisher eventPublisher;
    private final MissionRunRepository missionRunRepository;
    private final SimulationSessionRepository simulationSessionRepository;
    private final Map<String, Observation> observations = new ConcurrentHashMap<>();
    private final DeviceCodeMapper deviceCodeMapper = new DeviceCodeMapper();
    private final Map<String, UnityRuntimeSnapshot> unityRuntimeSnapshots = new ConcurrentHashMap<>();
    private final Map<String, DeviceStatusSnapshot> deviceStatusSnapshots = new ConcurrentHashMap<>();
    private volatile boolean gatewayConnected;
    private final int heartbeatTimeoutSeconds;
    private final int telemetryRetentionDays;
    private final String rosHost;
    private final Integer rosPort;

    public RuntimeStateService(
            DeviceRepository deviceRepository,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            DeviceStatusEventRepository statusEventRepository,
            DeviceTelemetryRepository telemetryRepository,
            RuntimeEventPublisher eventPublisher,
            MissionRunRepository missionRunRepository,
            SimulationSessionRepository simulationSessionRepository,
            @Value("${app.runtime.heartbeat-timeout-seconds:5}") int heartbeatTimeoutSeconds,
            @Value("${app.runtime.telemetry-retention-days:7}") int telemetryRetentionDays,
            @Value("${app.runtime.ros-websocket-url}") String rosWebSocketUrl
    ) {
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
        this.statusEventRepository = statusEventRepository;
        this.telemetryRepository = telemetryRepository;
        this.eventPublisher = eventPublisher;
        this.missionRunRepository = missionRunRepository;
        this.simulationSessionRepository = simulationSessionRepository;
        this.heartbeatTimeoutSeconds = heartbeatTimeoutSeconds;
        this.telemetryRetentionDays = telemetryRetentionDays;
        URI uri = URI.create(rosWebSocketUrl);
        this.rosHost = uri.getHost();
        this.rosPort = uri.getPort() < 0 ? null : uri.getPort();
    }

    public void observeRosConnection(boolean connected, String detail) {
        LocalDateTime now = LocalDateTime.now();
        observations.put(ROS_CODE, new Observation(now, connected, "ROS_WEBSOCKET", "ros-websocket",
                null, rosHost, rosPort, null, detail));
    }

    public void observeRosFrame(RosPoseFrame frame) {
        LocalDateTime now = LocalDateTime.now();
        observations.put(ROS_CODE, new Observation(now, true, "ROS_WEBSOCKET", "ros-websocket",
                frame.sequence(), rosHost, rosPort, null, "正在接收 Gazebo 位姿数据"));
        if (frame.hasFleetVehicles()) {
            observeFleetPoses(frame, now);
            return;
        }
        observePose(USV_CODE, frame.boat(), frame.sequence(), now);
        observePose(UAV_CODE, frame.drone(), frame.sequence(), now);
    }

    public void observeGatewayHeartbeat(String instanceId, long sequence) {
        LocalDateTime now = LocalDateTime.now();
        observations.put(ROS_CODE, new Observation(now, true, "ROS_GATEWAY_V1", instanceId,
                sequence, rosHost, rosPort, null, "ROS Gateway v1 heartbeat sequence " + sequence));
    }

    public void observeGatewayConnection(boolean connected) {
        gatewayConnected = connected;
    }

    public void observeGatewayDeviceStatus(JsonNode payload, String source, String streamId, long sequence) {
        if (payload == null) return;
        String deviceCode = normalizeGatewayDeviceCode(payload.path("deviceCode").asText(""));
        if (deviceCode == null) return;
        deviceStatusSnapshots.put(deviceCode, new DeviceStatusSnapshot(
                deviceCode,
                payload.path("connectionState").asText("UNKNOWN").trim().toUpperCase(),
                payload.path("operationState").asText("UNKNOWN").trim().toUpperCase(),
                payload.path("controlMode").asText("UNKNOWN").trim().toUpperCase(),
                payload.path("flightState").asText("UNKNOWN").trim().toUpperCase(),
                payload.path("armed").asBoolean(false),
                payload.path("activeCommandId").asText(""),
                LocalDateTime.now(),
                sequence,
                source,
                streamId
        ));
    }

    public ControlOperationalSnapshot getControlOperationalSnapshot(String deviceCode) {
        String normalized = deviceCode == null ? "" : deviceCode.trim().toLowerCase().replace('_', '-');
        if (!normalized.startsWith("uav-") && !normalized.startsWith("usv-")) {
            return new ControlOperationalSnapshot("UNKNOWN", false, null, "UNKNOWN");
        }
        DeviceStatusSnapshot snapshot = deviceStatusSnapshots.get(normalized);
        if (snapshot == null) {
            return new ControlOperationalSnapshot("UNKNOWN", false, null, "UNKNOWN");
        }
        boolean fresh = gatewayConnected
                && Duration.between(snapshot.receivedAt(), LocalDateTime.now()).compareTo(Duration.ofSeconds(2)) <= 0;
        boolean online = "ONLINE".equals(snapshot.connectionState());
        String state = normalized.startsWith("usv-")
                ? mapUsvOperationalState(snapshot)
                : mapUavOperationalState(snapshot);
        return new ControlOperationalSnapshot(
                fresh && online ? state : "UNKNOWN",
                fresh,
                snapshot.receivedAt(),
                snapshot.connectionState()
        );
    }

    private String mapUavOperationalState(DeviceStatusSnapshot snapshot) {
        if ("GROUNDED".equals(snapshot.flightState()) || "AIRBORNE".equals(snapshot.flightState())) {
            return snapshot.flightState();
        }
        if ("HOVERING".equals(snapshot.operationState()) || "LOITER".equals(snapshot.controlMode())) {
            return "HOLDING";
        }
        if ("RETURNING".equals(snapshot.operationState()) || "RTL".equals(snapshot.controlMode())) {
            return "RETURNING";
        }
        if ("LANDING".equals(snapshot.operationState())) {
            return "LANDING";
        }
        return "UNKNOWN";
    }

    private String mapUsvOperationalState(DeviceStatusSnapshot snapshot) {
        if ("IDLE".equals(snapshot.operationState())) {
            return "MOORED";
        }
        if ("HOLD".equals(snapshot.operationState())
                || "HOLDING".equals(snapshot.operationState())
                || "HOLD".equals(snapshot.controlMode())) {
            return "HOLDING";
        }
        if ("SAILING".equals(snapshot.operationState())
                || "MOVING".equals(snapshot.operationState())
                || "AUTO".equals(snapshot.controlMode())) {
            return "SAILING";
        }
        if ("RETURNING".equals(snapshot.operationState()) || "RTL".equals(snapshot.controlMode())) {
            return "RETURNING";
        }
        if ("STOPPED".equals(snapshot.operationState())) {
            return "STOPPED";
        }
        if ("ERROR".equals(snapshot.operationState())) {
            return "ERROR";
        }
        return "UNKNOWN";
    }

    public TakeoffReadiness getUavTakeoffReadiness(String deviceCode) {
        String normalized = deviceCode == null ? "" : deviceCode.trim().toLowerCase().replace('_', '-');
        if (!normalized.startsWith("uav-")) {
            return new TakeoffReadiness(false, "TARGET_IS_NOT_UAV", "target is not a UAV", "UNKNOWN", null);
        }
        Observation observation = observations.get(normalized);
        boolean poseFresh = observation != null
                && observation.online()
                && Duration.between(observation.observedAt(), LocalDateTime.now()).getSeconds() <= heartbeatTimeoutSeconds;
        Double altitude = poseFresh && observation.pose() != null ? observation.pose().positionY() : null;
        if (altitude != null && altitude > 1.0) {
            return new TakeoffReadiness(
                    false,
                    "UAV_ALREADY_AIRBORNE",
                    "UAV takeoff rejected because current altitude is " + String.format("%.2f", altitude) + " m",
                    "AIRBORNE",
                    altitude
            );
        }

        ControlOperationalSnapshot control = getControlOperationalSnapshot(normalized);
        if (!control.fresh()) {
            return new TakeoffReadiness(
                    false,
                    "UAV_CONTROL_STATE_STALE",
                    "UAV takeoff requires a fresh ROS Gateway device.status frame",
                    control.state(),
                    altitude
            );
        }
        if (!"ONLINE".equals(control.connectionState())) {
            return new TakeoffReadiness(
                    false,
                    "UAV_CONTROL_OFFLINE",
                    "UAV takeoff requires an online control connection",
                    control.state(),
                    altitude
            );
        }
        if (!"GROUNDED".equals(control.state())) {
            return new TakeoffReadiness(
                    false,
                    "UAV_NOT_GROUNDED",
                    "UAV takeoff requires GROUNDED state, current state is " + control.state(),
                    control.state(),
                    altitude
            );
        }
        return new TakeoffReadiness(true, null, "UAV is grounded and ready for takeoff", control.state(), altitude);
    }

    public void observeGatewayPoseBatch(JsonNode payload, long sequence) {
        if (payload == null || !payload.path("vehicles").isArray()) {
            return;
        }
        LocalDateTime now = LocalDateTime.now();
        observations.put(ROS_CODE, new Observation(now, true, "ROS_GATEWAY_V1", "ros-gateway-v1",
                sequence, rosHost, rosPort, null, "ROS Gateway v1 pose batch sequence " + sequence));
        payload.path("vehicles").forEach(vehicle -> observeGatewayVehiclePose(vehicle, sequence, now));
    }

    public void observeUnityHeartbeat(IntegrationHeartbeatRequest request, String host) {
        boolean online = !request.state().equalsIgnoreCase("STOPPED")
                && !request.state().equalsIgnoreCase("OFFLINE")
                && !request.state().equalsIgnoreCase("FAILED");
        String detail = request.detail();
        if (request.rosConnectionStatus() != null && !request.rosConnectionStatus().isBlank()) {
            detail = (detail == null || detail.isBlank() ? "" : detail + " | ") + request.rosConnectionStatus();
        }
        RuntimeScope scope = request.runtimeScope() == null ? RuntimeScope.SYSTEM_OVERVIEW : request.runtimeScope();
        Observation observation = new Observation(LocalDateTime.now(), online, "UNITY_HEARTBEAT",
                request.instanceId(), null, host, null, null, detail);
        observations.put(unityObservationKey(scope), observation);
        Set<String> deviceCodes = request.deviceCodes() == null
                ? Set.of()
                : request.deviceCodes().stream()
                        .filter(code -> code != null && !code.isBlank())
                        .map(code -> code.trim().toLowerCase())
                        .collect(Collectors.toUnmodifiableSet());
        unityRuntimeSnapshots.put(unityObservationKey(scope), new UnityRuntimeSnapshot(
                request.instanceId(),
                Boolean.TRUE.equals(request.controlsReady()),
                deviceCodes,
                request.trajectorySequence(),
                LocalDateTime.now()
        ));
        if (scope == RuntimeScope.SYSTEM_OVERVIEW) {
            observations.put(UNITY_CODE, observation);
        }
    }

    public boolean isUnityOnline(RuntimeScope scope) {
        return isObservationOnline(unityObservationKey(scope));
    }

    public boolean isUnityOnline(RuntimeScope scope, String instanceId) {
        Observation observation = observations.get(unityObservationKey(scope));
        return observation != null
                && (instanceId == null || instanceId.isBlank() || instanceId.equals(observation.instanceId()))
                && observation.online()
                && Duration.between(observation.observedAt(), LocalDateTime.now()).getSeconds() <= heartbeatTimeoutSeconds;
    }

    public boolean isOnline(String code) {
        return isObservationOnline(code);
    }

    public UnityRuntimeSnapshot getUnityRuntimeSnapshot(RuntimeScope scope, String instanceId) {
        UnityRuntimeSnapshot snapshot = unityRuntimeSnapshots.get(unityObservationKey(scope));
        if (snapshot == null
                || (instanceId != null && !instanceId.isBlank() && !instanceId.equals(snapshot.instanceId()))
                || Duration.between(snapshot.observedAt(), LocalDateTime.now()).getSeconds() > heartbeatTimeoutSeconds) {
            return null;
        }
        return snapshot;
    }

    private boolean isObservationOnline(String key) {
        Observation observation = observations.get(key);
        return observation != null && observation.online()
                && Duration.between(observation.observedAt(), LocalDateTime.now()).getSeconds() <= heartbeatTimeoutSeconds;
    }

    private String unityObservationKey(RuntimeScope scope) {
        return UNITY_CODE + ":" + scope.name();
    }

    @Transactional
    public void markRuntimeStopped(String detail) {
        LocalDateTime now = LocalDateTime.now();
        observations.clear();
        unityRuntimeSnapshots.clear();
        deviceStatusSnapshots.clear();
        gatewayConnected = false;
        for (Device device : deviceRepository.findAllByDeletedFalse(Sort.by(Sort.Direction.ASC, "id"))) {
            if (!RUNTIME_TYPES.contains(device.getType())) {
                continue;
            }

            RuntimeDeviceStatus runtime = runtimeStatusRepository.findByDeviceId(device.getId())
                    .orElseGet(() -> new RuntimeDeviceStatus(device.getId()));
            DeviceStatus previous = runtime.getStatus();
            runtime.markOffline(detail);
            runtimeStatusRepository.save(runtime);

            if (device.getStatus() != DeviceStatus.OFFLINE) {
                device.updateRuntimeStatus(DeviceStatus.OFFLINE);
            }
            if (previous != DeviceStatus.OFFLINE) {
                statusEventRepository.save(new DeviceStatusEvent(device.getId(), previous, DeviceStatus.OFFLINE,
                        runtime.getSource(), detail, now));
            }
        }
        eventPublisher.publishRuntimeChange();
    }

    @Scheduled(fixedDelay = 1000)
    @Transactional
    public void reconcileRuntimeState() {
        LocalDateTime now = LocalDateTime.now();
        Long activeRunId = missionRunRepository.findFirstByStatusInOrderByStartedAtDesc(
                        EnumSet.of(MissionRunStatus.RUNNING, MissionRunStatus.PAUSED))
                .map(run -> run.getId())
                .orElse(null);
        Long activeSessionId = simulationSessionRepository.findFirstByStatusInOrderByCreatedAtDesc(EnumSet.of(
                        SimulationStatus.STARTING,
                        SimulationStatus.RUNNING,
                        SimulationStatus.PARTIAL
                ))
                .map(session -> session.getId())
                .orElse(null);
        for (Device device : deviceRepository.findAllByDeletedFalse(Sort.by(Sort.Direction.ASC, "id"))) {
            if (!RUNTIME_TYPES.contains(device.getType())) {
                continue;
            }

            Observation observation = observations.get(device.getCode());
            boolean online = observation != null && observation.online()
                    && Duration.between(observation.observedAt(), now).getSeconds() <= heartbeatTimeoutSeconds;
            RuntimeDeviceStatus runtime = runtimeStatusRepository.findByDeviceId(device.getId())
                    .orElseGet(() -> new RuntimeDeviceStatus(device.getId()));
            DeviceStatus previous = runtime.getStatus();

            if (online) {
                runtime.observe(observation.source(), observation.instanceId(), observation.observedAt(),
                        observation.sequence(), observation.host(), observation.port(), observation.pose(), observation.detail());
            } else {
                runtime.markOffline(observation == null ? "尚未收到真实心跳" : "心跳超时或组件已停止");
            }

            runtimeStatusRepository.save(runtime);
            if (previous != runtime.getStatus()) {
                statusEventRepository.save(new DeviceStatusEvent(device.getId(), previous, runtime.getStatus(),
                        runtime.getSource(), runtime.getDetail(), now));
            }
            if (online && observation.pose() != null
                    && (device.getType() == DeviceType.UAV || device.getType() == DeviceType.USV)) {
                telemetryRepository.save(new DeviceTelemetry(
                        device.getId(),
                        activeRunId,
                        activeSessionId,
                        now,
                        observation.sequence(),
                        observation.pose(),
                        observation.source()
                ));
            }
        }
        publishRuntimeChangeAfterCommit();
    }

    private void publishRuntimeChangeAfterCommit() {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            eventPublisher.publishRuntimeChange();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                eventPublisher.publishRuntimeChange();
            }
        });
    }

    @Scheduled(cron = "0 15 3 * * *")
    @Transactional
    public void removeExpiredTelemetry() {
        telemetryRepository.deleteOlderThan(LocalDateTime.now().minusDays(telemetryRetentionDays));
    }

    private void observePose(String code, RosPoseFrame.PoseData poseData, long sequence, LocalDateTime observedAt) {
        if (poseData == null || !poseData.valid()) {
            return;
        }
        double[] p = poseData.position();
        double[] q = poseData.orientation();
        RuntimePose pose = new RuntimePose(p[0], p[1], p[2], q[0], q[1], q[2], q[3]);
        observations.put(code, new Observation(observedAt, true, "ROS_WEBSOCKET", "gazebo",
                sequence, rosHost, rosPort, pose, "Gazebo 位姿序号 " + sequence));
    }

    private void observeFleetPoses(RosPoseFrame frame, LocalDateTime observedAt) {
        if (frame.usvs() != null) {
            frame.usvs().forEach(vehicle -> observeVehiclePose(vehicle, frame.sequence(), observedAt));
        }
        if (frame.uavs() != null) {
            frame.uavs().forEach(vehicle -> observeVehiclePose(vehicle, frame.sequence(), observedAt));
        }
    }

    private void observeVehiclePose(RosPoseFrame.VehiclePoseData vehicle, long sequence, LocalDateTime observedAt) {
        if (vehicle == null || vehicle.id() == null || vehicle.id().isBlank()) {
            return;
        }
        String code = vehicle.id().trim().toLowerCase().replace('_', '-');
        if (!code.matches("(uav|usv)-0[1-3]")) {
            return;
        }
        observePose(code, vehicle.poseData(), sequence, observedAt);
    }

    private void observeGatewayVehiclePose(JsonNode vehicle, long sequence, LocalDateTime observedAt) {
        if (!vehicle.path("fresh").asBoolean(false) || !vehicle.path("positionValid").asBoolean(false)) {
            return;
        }
        String code = normalizeGatewayDeviceCode(vehicle.path("deviceCode").asText(""));
        if (code == null) {
            return;
        }
        Optional<RuntimePose> pose = gatewayPose(vehicle);
        observations.put(code, new Observation(observedAt, true, "ROS_GATEWAY_V1", "ros-gateway-v1",
                sequence, rosHost, rosPort, pose.orElse(null), "ROS Gateway v1 pose batch sequence " + sequence));
    }

    private String normalizeGatewayDeviceCode(String code) {
        if (code == null || code.isBlank()) {
            return null;
        }
        try {
            return deviceCodeMapper.toPlatform(code);
        } catch (IllegalArgumentException ignored) {
            return null;
        }
    }

    private Optional<RuntimePose> gatewayPose(JsonNode vehicle) {
        JsonNode position = vehicle.path("localPositionEnuM");
        if (!position.path("x").isNumber() || !position.path("y").isNumber() || !position.path("z").isNumber()) {
            return Optional.empty();
        }
        JsonNode orientation = vehicle.path("orientation");
        double orientationX = orientation.path("x").isNumber() ? orientation.path("x").asDouble() : 0.0;
        double orientationY = orientation.path("y").isNumber() ? orientation.path("y").asDouble() : 0.0;
        double orientationZ = orientation.path("z").isNumber() ? orientation.path("z").asDouble() : 0.0;
        double orientationW = orientation.path("w").isNumber() ? orientation.path("w").asDouble() : 1.0;
        return Optional.of(new RuntimePose(
                position.path("x").asDouble(),
                position.path("y").asDouble(),
                position.path("z").asDouble(),
                orientationX,
                orientationY,
                orientationZ,
                orientationW
        ));
    }

    private record Observation(
            LocalDateTime observedAt,
            boolean online,
            String source,
            String instanceId,
            Long sequence,
            String host,
            Integer port,
            RuntimePose pose,
            String detail
    ) {
    }

    public record UnityRuntimeSnapshot(
            String instanceId,
            boolean controlsReady,
            Set<String> deviceCodes,
            Long trajectorySequence,
            LocalDateTime observedAt
    ) {
    }

    private record DeviceStatusSnapshot(
            String deviceCode,
            String connectionState,
            String operationState,
            String controlMode,
            String flightState,
            boolean armed,
            String activeCommandId,
            LocalDateTime receivedAt,
            long sequence,
            String source,
            String streamId
    ) {
    }

    public record ControlOperationalSnapshot(
            String state,
            boolean fresh,
            LocalDateTime receivedAt,
            String connectionState
    ) {
    }

    public record TakeoffReadiness(
            boolean allowed,
            String errorCode,
            String detail,
            String state,
            Double altitude
    ) {
    }
}
