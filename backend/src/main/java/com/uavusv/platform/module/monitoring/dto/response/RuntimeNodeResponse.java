package com.uavusv.platform.module.monitoring.dto.response;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;

import java.time.Duration;
import java.time.LocalDateTime;

public record RuntimeNodeResponse(
        Long id,
        String code,
        String name,
        DeviceType type,
        DeviceStatus status,
        String host,
        Integer port,
        String endpoint,
        String rosNamespace,
        LocalDateTime lastHeartbeatAt,
        long heartbeatAgeSeconds,
        String source,
        String instanceId,
        Double positionX,
        Double positionY,
        Double positionZ,
        String detail
) {
    public static RuntimeNodeResponse from(Device device, RuntimeDeviceStatus runtime, LocalDateTime now) {
        LocalDateTime lastHeartbeatAt = runtime == null ? null : runtime.getLastHeartbeatAt();
        long heartbeatAgeSeconds = lastHeartbeatAt == null
                ? -1
                : Math.max(0, Duration.between(lastHeartbeatAt, now).getSeconds());

        return new RuntimeNodeResponse(
                device.getId(),
                device.getCode(),
                device.getName(),
                device.getType(),
                runtime == null ? DeviceStatus.UNKNOWN : runtime.getStatus(),
                runtime != null && runtime.getHost() != null ? runtime.getHost() : device.getHost(),
                runtime != null && runtime.getPort() != null ? runtime.getPort() : device.getPort(),
                buildEndpoint(device, runtime),
                device.getRosNamespace(),
                lastHeartbeatAt,
                heartbeatAgeSeconds,
                runtime == null ? "REGISTRY" : runtime.getSource(),
                runtime == null ? null : runtime.getInstanceId(),
                runtime == null ? null : runtime.getPositionX(),
                runtime == null ? null : runtime.getPositionY(),
                runtime == null ? null : runtime.getPositionZ(),
                runtime == null ? "尚未收到真实心跳" : runtime.getDetail()
        );
    }

    public static RuntimeNodeResponse offline(Device device, String detail) {
        return new RuntimeNodeResponse(
                device.getId(),
                device.getCode(),
                device.getName(),
                device.getType(),
                DeviceStatus.OFFLINE,
                device.getHost(),
                device.getPort(),
                buildEndpoint(device, null),
                device.getRosNamespace(),
                null,
                -1,
                "CONTROL_SESSION",
                null,
                null,
                null,
                null,
                detail
        );
    }

    private static String buildEndpoint(Device device, RuntimeDeviceStatus runtime) {
        String host = runtime != null && runtime.getHost() != null ? runtime.getHost() : device.getHost();
        Integer port = runtime != null && runtime.getPort() != null ? runtime.getPort() : device.getPort();
        if (host == null || host.isBlank()) {
            return port == null ? "" : ":" + port;
        }
        return port == null ? host : host + ":" + port;
    }
}
