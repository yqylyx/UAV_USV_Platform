package com.uavusv.platform.module.monitoring.service.impl;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeNodeResponse;
import com.uavusv.platform.module.monitoring.dto.response.RuntimeSummaryResponse;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import com.uavusv.platform.module.monitoring.service.MonitoringService;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
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
    private final SimulationSessionRepository sessionRepository;

    public MonitoringServiceImpl(
            DeviceRepository deviceRepository,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            SimulationSessionRepository sessionRepository
    ) {
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
        this.sessionRepository = sessionRepository;
    }

    @Override
    public RuntimeSummaryResponse getSummary() {
        List<Device> nodes = loadRuntimeDevices();
        Map<Long, RuntimeDeviceStatus> runtimeStatuses = loadRuntimeStatuses(nodes);
        LocalDateTime refreshedAt = LocalDateTime.now();
        boolean runtimeActive = hasActiveRuntimeSession();

        return new RuntimeSummaryResponse(
                nodes.size(),
                runtimeActive ? countByStatus(nodes, runtimeStatuses, DeviceStatus.ONLINE) : 0,
                runtimeActive ? countByStatus(nodes, runtimeStatuses, DeviceStatus.OFFLINE) : nodes.size(),
                runtimeActive ? countByStatus(nodes, runtimeStatuses, DeviceStatus.MAINTENANCE) : 0,
                runtimeActive ? countByStatus(nodes, runtimeStatuses, DeviceStatus.UNKNOWN) : 0,
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
        boolean runtimeActive = hasActiveRuntimeSession();
        return devices.stream()
                .filter(device -> type == null || device.getType() == type)
                .map(device -> runtimeActive
                        ? RuntimeNodeResponse.from(device, runtimeStatuses.get(device.getId()), now)
                        : RuntimeNodeResponse.offline(device, "平台仿真未运行，等待点击运行后接入真实心跳"))
                .filter(node -> status == null || node.status() == status)
                .toList();
    }

    private boolean hasActiveRuntimeSession() {
        return sessionRepository.findFirstByStatusInOrderByCreatedAtDesc(EnumSet.of(
                SimulationStatus.STARTING,
                SimulationStatus.RUNNING,
                SimulationStatus.PARTIAL,
                SimulationStatus.STOPPING
        )).isPresent();
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

    private long countByStatus(List<Device> nodes, Map<Long, RuntimeDeviceStatus> runtimes, DeviceStatus status) {
        return nodes.stream()
                .filter(device -> runtimes.containsKey(device.getId()) && runtimes.get(device.getId()).getStatus() == status)
                .count();
    }

    private long countByType(List<Device> nodes, DeviceType type) {
        return nodes.stream().filter(device -> device.getType() == type).count();
    }
}
