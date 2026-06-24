package com.uavusv.platform.module.monitoring.service;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.monitoring.dto.request.IntegrationHeartbeatRequest;
import com.uavusv.platform.module.monitoring.dto.request.RosPoseFrame;
import com.uavusv.platform.module.monitoring.entity.DeviceStatusEvent;
import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.entity.RuntimePose;
import com.uavusv.platform.module.monitoring.repository.DeviceStatusEventRepository;
import com.uavusv.platform.module.monitoring.repository.DeviceTelemetryRepository;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.EnumSet;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class RuntimeStateService {

    public static final String UAV_CODE = "uav-01";
    public static final String USV_CODE = "usv-01";
    public static final String ROS_CODE = "ros-bridge-01";
    public static final String UNITY_CODE = "unity-client-01";

    private static final EnumSet<DeviceType> RUNTIME_TYPES = EnumSet.of(
            DeviceType.UAV, DeviceType.USV, DeviceType.ROS_NODE, DeviceType.UNITY_NODE
    );

    private final DeviceRepository deviceRepository;
    private final RuntimeDeviceStatusRepository runtimeStatusRepository;
    private final DeviceStatusEventRepository statusEventRepository;
    private final DeviceTelemetryRepository telemetryRepository;
    private final RuntimeEventPublisher eventPublisher;
    private final Map<String, Observation> observations = new ConcurrentHashMap<>();
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
            @Value("${app.runtime.heartbeat-timeout-seconds:5}") int heartbeatTimeoutSeconds,
            @Value("${app.runtime.telemetry-retention-days:7}") int telemetryRetentionDays,
            @Value("${app.runtime.ros-websocket-url}") String rosWebSocketUrl
    ) {
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
        this.statusEventRepository = statusEventRepository;
        this.telemetryRepository = telemetryRepository;
        this.eventPublisher = eventPublisher;
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
        observePose(USV_CODE, frame.boat(), frame.sequence(), now);
        observePose(UAV_CODE, frame.drone(), frame.sequence(), now);
    }

    public void observeUnityHeartbeat(IntegrationHeartbeatRequest request, String host) {
        boolean online = !request.state().equalsIgnoreCase("STOPPED")
                && !request.state().equalsIgnoreCase("OFFLINE")
                && !request.state().equalsIgnoreCase("FAILED");
        String detail = request.detail();
        if (request.rosConnectionStatus() != null && !request.rosConnectionStatus().isBlank()) {
            detail = (detail == null || detail.isBlank() ? "" : detail + " | ") + request.rosConnectionStatus();
        }
        observations.put(UNITY_CODE, new Observation(LocalDateTime.now(), online, "UNITY_HEARTBEAT",
                request.instanceId(), null, host, null, null, detail));
    }

    public boolean isOnline(String code) {
        Observation observation = observations.get(code);
        return observation != null && observation.online()
                && Duration.between(observation.observedAt(), LocalDateTime.now()).getSeconds() <= heartbeatTimeoutSeconds;
    }

    @Scheduled(fixedDelay = 1000)
    @Transactional
    public void reconcileRuntimeState() {
        LocalDateTime now = LocalDateTime.now();
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
            if (device.getStatus() != runtime.getStatus()) {
                device.updateRuntimeStatus(runtime.getStatus());
            }
            if (previous != runtime.getStatus()) {
                statusEventRepository.save(new DeviceStatusEvent(device.getId(), previous, runtime.getStatus(),
                        runtime.getSource(), runtime.getDetail(), now));
            }
            if (online && observation.pose() != null
                    && (device.getType() == DeviceType.UAV || device.getType() == DeviceType.USV)) {
                telemetryRepository.save(new DeviceTelemetry(device.getId(), now, observation.sequence(), observation.pose()));
            }
        }
        eventPublisher.publishRuntimeChange();
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
}
