package com.uavusv.platform.module.monitoring.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.repository.DeviceStatusEventRepository;
import com.uavusv.platform.module.monitoring.repository.DeviceTelemetryRepository;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import com.uavusv.platform.module.monitoring.service.impl.MonitoringServiceImpl;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RuntimeStateServiceGatewayV1Tests {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void authoritativeDeviceStatusIsExposedAndFailsClosed() throws Exception {
        Device device = device("uav-01", DeviceType.UAV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);
        JsonNode grounded = objectMapper.readTree("""
                {"deviceCode":"uav_01","connectionState":"ONLINE","flightState":"GROUNDED","armed":false}
                """);

        services.runtimeStateService.observeGatewayConnection(true);
        services.runtimeStateService.observeGatewayDeviceStatus(
                grounded, "uav_usv_fleet_gateway", "device.status.uav_01", 1L);

        var groundedNode = services.monitoringService.listRuntimeNodes(null, null).get(0);
        assertThat(groundedNode.controlOperationalState()).isEqualTo("GROUNDED");
        assertThat(groundedNode.controlStateFresh()).isTrue();
        assertThat(groundedNode.controlConnectionState()).isEqualTo("ONLINE");

        services.runtimeStateService.observeGatewayConnection(false);
        var disconnectedNode = services.monitoringService.listRuntimeNodes(null, null).get(0);
        assertThat(disconnectedNode.controlOperationalState()).isEqualTo("UNKNOWN");
        assertThat(disconnectedNode.controlStateFresh()).isFalse();
    }

    @Test
    void unknownAndOfflineDeviceStatusAreNeverControllable() throws Exception {
        Device device = device("uav-01", DeviceType.UAV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);
        services.runtimeStateService.observeGatewayConnection(true);

        services.runtimeStateService.observeGatewayDeviceStatus(objectMapper.readTree(
                "{\"deviceCode\":\"uav_01\",\"connectionState\":\"ONLINE\",\"flightState\":\"UNKNOWN\"}"),
                "gateway", "device.status.uav_01", 1L);
        assertThat(services.runtimeStateService.getControlOperationalSnapshot("uav-01").state()).isEqualTo("UNKNOWN");

        services.runtimeStateService.observeGatewayDeviceStatus(objectMapper.readTree(
                "{\"deviceCode\":\"uav_01\",\"connectionState\":\"OFFLINE\",\"flightState\":\"GROUNDED\"}"),
                "gateway", "device.status.uav_01", 2L);
        assertThat(services.runtimeStateService.getControlOperationalSnapshot("uav-01").state()).isEqualTo("UNKNOWN");
    }

    @Test
    void airborneAndExpiredDeviceStatusAreHandledAuthoritatively() throws Exception {
        Device device = device("uav-01", DeviceType.UAV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);
        services.runtimeStateService.observeGatewayConnection(true);
        services.runtimeStateService.observeGatewayDeviceStatus(objectMapper.readTree(
                "{\"deviceCode\":\"uav_01\",\"connectionState\":\"ONLINE\",\"flightState\":\"AIRBORNE\"}"),
                "gateway", "device.status.uav_01", 1L);

        assertThat(services.runtimeStateService.getControlOperationalSnapshot("uav-01").state()).isEqualTo("AIRBORNE");
        Thread.sleep(2100);
        assertThat(services.runtimeStateService.getControlOperationalSnapshot("uav-01").state()).isEqualTo("UNKNOWN");
        assertThat(services.runtimeStateService.getControlOperationalSnapshot("uav-01").fresh()).isFalse();
    }

    @Test
    void usvFlightStateNeverBecomesUavControlAuthority() throws Exception {
        Device device = device("usv-01", DeviceType.USV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);
        services.runtimeStateService.observeGatewayConnection(true);
        services.runtimeStateService.observeGatewayDeviceStatus(objectMapper.readTree(
                "{\"deviceCode\":\"usv_01\",\"connectionState\":\"ONLINE\",\"flightState\":\"GROUNDED\"}"),
                "gateway", "device.status.usv_01", 1L);

        assertThat(services.runtimeStateService.getControlOperationalSnapshot("usv-01").state()).isEqualTo("UNKNOWN");
    }

    @Test
    void gatewayPoseBatchUpdatesVehicleOnlineState() throws Exception {
        Device device = device("uav-01", DeviceType.UAV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);

        JsonNode payload = objectMapper.readTree("""
                {
                  "vehicles": [
                    {
                      "deviceCode": "uav_01",
                      "fresh": true,
                      "positionValid": true,
                      "localPositionEnuM": { "x": 12.5, "y": 3.0, "z": -8.25 },
                      "orientation": { "x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0 }
                    }
                  ]
                }
                """);

        services.runtimeStateService.observeGatewayPoseBatch(payload, 42L);
        services.runtimeStateService.reconcileRuntimeState();

        assertThat(runtime.getStatus()).isEqualTo(DeviceStatus.ONLINE);
        assertThat(runtime.getSource()).isEqualTo("ROS_GATEWAY_V1");
        assertThat(runtime.getLastHeartbeatAt()).isNotNull();
        assertThat(Duration.between(runtime.getLastHeartbeatAt(), LocalDateTime.now()).getSeconds()).isLessThanOrEqualTo(1);
        assertThat(runtime.getPositionX()).isEqualTo(12.5);
        assertThat(runtime.getPositionY()).isEqualTo(3.0);
        assertThat(runtime.getPositionZ()).isEqualTo(-8.25);
        assertThat(device.getStatus()).isEqualTo(DeviceStatus.UNKNOWN);
        verify(services.runtimeStatusRepository).save(runtime);
        verify(services.telemetryRepository).save(any());

        var nodes = services.monitoringService.listRuntimeNodes(null, null);
        assertThat(nodes).hasSize(1);
        assertThat(nodes.get(0).status()).isEqualTo(DeviceStatus.ONLINE);
        assertThat(nodes.get(0).heartbeatAgeSeconds()).isLessThanOrEqualTo(1);
        assertThat(nodes.get(0).detail()).contains("ROS Gateway v1 pose batch sequence 42");
    }

    @Test
    void gatewayPoseBatchDoesNotMarkStaleVehicleOnline() throws Exception {
        Device device = device("uav-01", DeviceType.UAV);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(device.getId());
        TestServices services = services(List.of(device), runtime);

        JsonNode payload = objectMapper.readTree("""
                {
                  "vehicles": [
                    {
                      "deviceCode": "uav_01",
                      "fresh": false,
                      "positionValid": true,
                      "localPositionEnuM": { "x": 12.5, "y": 3.0, "z": -8.25 }
                    }
                  ]
                }
                """);

        services.runtimeStateService.observeGatewayPoseBatch(payload, 43L);
        services.runtimeStateService.reconcileRuntimeState();

        assertThat(runtime.getStatus()).isEqualTo(DeviceStatus.OFFLINE);
        assertThat(runtime.getLastHeartbeatAt()).isNull();
    }

    @Test
    void gatewayHeartbeatOnlyUpdatesRosBridgeNode() {
        Device rosBridge = device("ros-bridge-01", DeviceType.ROS_NODE);
        RuntimeDeviceStatus runtime = new RuntimeDeviceStatus(rosBridge.getId());
        TestServices services = services(List.of(rosBridge), runtime);

        services.runtimeStateService.observeGatewayHeartbeat("gateway-1", 44L);
        services.runtimeStateService.reconcileRuntimeState();

        assertThat(runtime.getStatus()).isEqualTo(DeviceStatus.ONLINE);
        assertThat(runtime.getInstanceId()).isEqualTo("gateway-1");
        assertThat(runtime.getDetail()).contains("ROS Gateway v1 heartbeat sequence 44");
    }

    @Test
    void publishesRuntimeChangeOnlyAfterCommit() {
        Device rosBridge = device("ros-bridge-01", DeviceType.ROS_NODE);
        TestServices services = services(List.of(rosBridge), new RuntimeDeviceStatus(rosBridge.getId()));

        TransactionSynchronizationManager.initSynchronization();
        try {
            services.runtimeStateService.observeGatewayHeartbeat("gateway-1", 45L);
            services.runtimeStateService.reconcileRuntimeState();
            verify(services.eventPublisher, never()).publishRuntimeChange();

            TransactionSynchronizationManager.getSynchronizations()
                    .forEach(TransactionSynchronization::afterCommit);
            verify(services.eventPublisher).publishRuntimeChange();
        } finally {
            TransactionSynchronizationManager.clearSynchronization();
        }
    }

    @Test
    void doesNotPublishRuntimeChangeAfterRollback() {
        Device rosBridge = device("ros-bridge-01", DeviceType.ROS_NODE);
        TestServices services = services(List.of(rosBridge), new RuntimeDeviceStatus(rosBridge.getId()));

        TransactionSynchronizationManager.initSynchronization();
        try {
            services.runtimeStateService.observeGatewayHeartbeat("gateway-1", 46L);
            services.runtimeStateService.reconcileRuntimeState();
            TransactionSynchronizationManager.getSynchronizations()
                    .forEach(sync -> sync.afterCompletion(TransactionSynchronization.STATUS_ROLLED_BACK));
            verify(services.eventPublisher, never()).publishRuntimeChange();
        } finally {
            TransactionSynchronizationManager.clearSynchronization();
        }
    }

    private TestServices services(List<Device> devices, RuntimeDeviceStatus runtime) {
        DeviceRepository deviceRepository = mock(DeviceRepository.class);
        RuntimeDeviceStatusRepository runtimeStatusRepository = mock(RuntimeDeviceStatusRepository.class);
        DeviceStatusEventRepository statusEventRepository = mock(DeviceStatusEventRepository.class);
        DeviceTelemetryRepository telemetryRepository = mock(DeviceTelemetryRepository.class);
        RuntimeEventPublisher eventPublisher = mock(RuntimeEventPublisher.class);
        MissionRunRepository missionRunRepository = mock(MissionRunRepository.class);
        SimulationSessionRepository simulationSessionRepository = mock(SimulationSessionRepository.class);

        when(deviceRepository.findAllByDeletedFalse(any(Sort.class))).thenReturn(devices);
        when(runtimeStatusRepository.findByDeviceId(runtime.getDeviceId())).thenReturn(Optional.of(runtime));
        when(runtimeStatusRepository.findAllByDeviceIdIn(anyCollection())).thenReturn(List.of(runtime));
        when(telemetryRepository.findLatestByDeviceIds(anyCollection())).thenReturn(List.of());
        when(missionRunRepository.findFirstByStatusInOrderByStartedAtDesc(any())).thenReturn(Optional.empty());
        when(simulationSessionRepository.findFirstByStatusInOrderByCreatedAtDesc(any())).thenReturn(Optional.empty());

        RuntimeStateService runtimeStateService = new RuntimeStateService(
                deviceRepository,
                runtimeStatusRepository,
                statusEventRepository,
                telemetryRepository,
                eventPublisher,
                missionRunRepository,
                simulationSessionRepository,
                5,
                7,
                "ws://10.16.59.251:8765/uav_usv/v1"
        );
        MonitoringServiceImpl monitoringService = new MonitoringServiceImpl(
                deviceRepository,
                runtimeStatusRepository,
                telemetryRepository,
                new GeoCoordinateService(false, 0, 0, "X", "Z"),
                runtimeStateService,
                10
        );
        return new TestServices(runtimeStateService, monitoringService, runtimeStatusRepository,
                telemetryRepository, eventPublisher);
    }

    private Device device(String code, DeviceType type) {
        Device device = new Device(code, code.toUpperCase(), type, DeviceStatus.UNKNOWN, "127.0.0.1", null, "/" + code, "test");
        ReflectionTestUtils.setField(device, "id", switch (code) {
            case "uav-01" -> 1L;
            case "ros-bridge-01" -> 4L;
            default -> 99L;
        });
        return device;
    }

    private record TestServices(
            RuntimeStateService runtimeStateService,
            MonitoringServiceImpl monitoringService,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            DeviceTelemetryRepository telemetryRepository,
            RuntimeEventPublisher eventPublisher
    ) {
    }
}
