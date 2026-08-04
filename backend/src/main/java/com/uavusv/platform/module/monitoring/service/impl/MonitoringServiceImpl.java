package com.uavusv.platform.module.monitoring.service.impl;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeNodeResponse;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeSummaryResponse;
import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.repository.DeviceTelemetryRepository;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import com.uavusv.platform.module.monitoring.service.GeoCoordinateService;
import com.uavusv.platform.module.monitoring.service.MonitoringService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
public class MonitoringServiceImpl implements MonitoringService {

    private static final EnumSet<DeviceType> RUNTIME_NODE_TYPES = EnumSet.of(
            DeviceType.UAV,
            DeviceType.USV,
            DeviceType.ROS_NODE,
            DeviceType.UNITY_NODE
    );

    private final DeviceRepository deviceRepository;
    private final RuntimeDeviceStatusRepository runtimeStatusRepository;
    private final DeviceTelemetryRepository telemetryRepository;
    private final GeoCoordinateService geoCoordinateService;
    private final int telemetryStaleSeconds;

    public MonitoringServiceImpl(
            DeviceRepository deviceRepository,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            DeviceTelemetryRepository telemetryRepository,
            GeoCoordinateService geoCoordinateService,
            @Value("${app.runtime.telemetry-stale-seconds:10}") int telemetryStaleSeconds
    ) {
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
        this.telemetryRepository = telemetryRepository;
        this.geoCoordinateService = geoCoordinateService;
        this.telemetryStaleSeconds = telemetryStaleSeconds;
    }

    @Override
    public RuntimeSummaryResponse getSummary() {
        List<Device> nodes = loadRuntimeDevices();
        Map<Long, RuntimeDeviceStatus> runtimeStatuses = loadRuntimeStatuses(nodes);
        LocalDateTime refreshedAt = LocalDateTime.now();

        return new RuntimeSummaryResponse(
                nodes.size(),
                countByStatus(nodes, runtimeStatuses, DeviceStatus.ONLINE),
                countByStatus(nodes, runtimeStatuses, DeviceStatus.OFFLINE),
                countByStatus(nodes, runtimeStatuses, DeviceStatus.MAINTENANCE),
                countByStatus(nodes, runtimeStatuses, DeviceStatus.UNKNOWN),
                countByType(nodes, DeviceType.ROS_NODE),
                countByType(nodes, DeviceType.UNITY_NODE),
                nodes.stream().filter(device -> device.getType() == DeviceType.UAV || device.getType() == DeviceType.USV).count(),
                refreshedAt
        );
    }

    @Override
    public List<RuntimeNodeResponse> listRuntimeNodes(DeviceType type, DeviceStatus status) {
        LocalDateTime now = LocalDateTime.now();
        List<Device> devices = loadRuntimeDevices();
        Map<Long, RuntimeDeviceStatus> runtimeStatuses = loadRuntimeStatuses(devices);
        Map<Long, DeviceTelemetry> latestTelemetry = loadLatestTelemetry(devices);
        return devices.stream()
                .filter(device -> type == null || device.getType() == type)
                .map(device -> RuntimeNodeResponse.from(
                        device,
                        runtimeStatuses.get(device.getId()),
                        latestTelemetry.get(device.getId()),
                        geoCoordinateService,
                        now,
                        telemetryStaleSeconds
                ))
                .filter(node -> status == null || node.status() == status)
                .toList();
    }

    private List<Device> loadRuntimeDevices() {
        return deviceRepository.findAllByDeletedFalse(Sort.by(Sort.Direction.ASC, "type", "name")).stream()
                .filter(device -> RUNTIME_NODE_TYPES.contains(device.getType()))
                .toList();
    }

    private Map<Long, RuntimeDeviceStatus> loadRuntimeStatuses(List<Device> devices) {
        return runtimeStatusRepository.findAllByDeviceIdIn(devices.stream().map(Device::getId).toList()).stream()
                .collect(Collectors.toMap(RuntimeDeviceStatus::getDeviceId, Function.identity()));
    }

    private Map<Long, DeviceTelemetry> loadLatestTelemetry(List<Device> devices) {
        List<Long> vehicleIds = devices.stream()
                .filter(device -> device.getType() == DeviceType.UAV || device.getType() == DeviceType.USV)
                .map(Device::getId)
                .toList();
        if (vehicleIds.isEmpty()) {
            return Map.of();
        }
        return telemetryRepository.findLatestByDeviceIds(vehicleIds).stream()
                .collect(Collectors.toMap(
                        DeviceTelemetry::getDeviceId,
                        Function.identity(),
                        (left, right) -> left.getRecordedAt().isAfter(right.getRecordedAt()) ? left : right
                ));
    }

    private long countByStatus(List<Device> nodes, Map<Long, RuntimeDeviceStatus> runtimes, DeviceStatus status) {
        return nodes.stream()
                .filter(device -> runtimes.containsKey(device.getId()) && runtimes.get(device.getId()).getStatus() == status)
                .count();
    }

    private long countByType(List<Device> nodes, DeviceType type) {
        return nodes.stream().filter(device -> device.getType() == type).count();
    }
}
