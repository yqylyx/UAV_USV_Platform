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

    public MonitoringServiceImpl(DeviceRepository deviceRepository, RuntimeDeviceStatusRepository runtimeStatusRepository) {
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
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
        return devices.stream()
                .filter(device -> type == null || device.getType() == type)
                .map(device -> RuntimeNodeResponse.from(device, runtimeStatuses.get(device.getId()), now))
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

    private long countByStatus(List<Device> nodes, Map<Long, RuntimeDeviceStatus> runtimes, DeviceStatus status) {
        return nodes.stream()
                .filter(device -> runtimes.containsKey(device.getId()) && runtimes.get(device.getId()).getStatus() == status)
                .count();
    }

    private long countByType(List<Device> nodes, DeviceType type) {
        return nodes.stream().filter(device -> device.getType() == type).count();
    }
}
