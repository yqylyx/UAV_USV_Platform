package com.uavusv.platform.module.monitoring.dto.response;

import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.service.GeoCoordinateService;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;

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
        Double latitude,
        Double longitude,
        Double batteryLevel,
        Integer linkQualityPercent,
        LocalDateTime telemetryAt,
        String telemetrySource,
        boolean telemetryStale,
        String controlOperationalState,
        boolean controlStateFresh,
        LocalDateTime controlStateReceivedAt,
        String controlConnectionState,
        String detail
) {
    public static RuntimeNodeResponse from(
            Device device,
            RuntimeDeviceStatus runtime,
            DeviceTelemetry telemetry,
            RuntimeStateService.ControlOperationalSnapshot controlState,
            GeoCoordinateService geoCoordinateService,
            LocalDateTime now,
            int telemetryStaleSeconds
    ) {
        LocalDateTime lastHeartbeatAt = runtime == null ? null : runtime.getLastHeartbeatAt();
        long heartbeatAgeSeconds = ageSeconds(lastHeartbeatAt, now);
        Double positionX = runtime != null && runtime.getPositionX() != null
                ? runtime.getPositionX()
                : telemetry == null ? null : telemetry.getPositionX();
        Double positionY = runtime != null && runtime.getPositionY() != null
                ? runtime.getPositionY()
                : telemetry == null ? null : telemetry.getPositionY();
        Double positionZ = runtime != null && runtime.getPositionZ() != null
                ? runtime.getPositionZ()
                : telemetry == null ? null : telemetry.getPositionZ();
        GeoCoordinateService.GeoCoordinate coordinate = geoCoordinateService.fromLocal(
                positionX,
                positionY,
                positionZ
        );
        LocalDateTime telemetryAt = telemetry != null ? telemetry.getRecordedAt() : lastHeartbeatAt;
        DeviceStatus status = runtime == null ? DeviceStatus.UNKNOWN : runtime.getStatus();

        return new RuntimeNodeResponse(
                device.getId(),
                device.getCode(),
                device.getName(),
                device.getType(),
                status,
                runtime != null && runtime.getHost() != null ? runtime.getHost() : device.getHost(),
                runtime != null && runtime.getPort() != null ? runtime.getPort() : device.getPort(),
                buildEndpoint(device, runtime),
                device.getRosNamespace(),
                lastHeartbeatAt,
                heartbeatAgeSeconds,
                runtime == null ? "REGISTRY" : runtime.getSource(),
                runtime == null ? null : runtime.getInstanceId(),
                positionX,
                positionY,
                positionZ,
                coordinate == null ? null : coordinate.latitude(),
                coordinate == null ? null : coordinate.longitude(),
                telemetry == null ? null : telemetry.getBatteryLevel(),
                linkQuality(status, heartbeatAgeSeconds, telemetryStaleSeconds),
                telemetryAt,
                telemetry == null ? runtime == null ? null : runtime.getSource() : telemetry.getSource(),
                isStale(telemetryAt, now, telemetryStaleSeconds),
                controlState.state(),
                controlState.fresh(),
                controlState.receivedAt(),
                controlState.connectionState(),
                runtime == null ? "尚未收到真实心跳" : runtime.getDetail()
        );
    }

    public static RuntimeNodeResponse offline(
            Device device,
            DeviceTelemetry telemetry,
            GeoCoordinateService geoCoordinateService,
            LocalDateTime now,
            int telemetryStaleSeconds,
            String detail
    ) {
        Double positionX = telemetry == null ? null : telemetry.getPositionX();
        Double positionY = telemetry == null ? null : telemetry.getPositionY();
        Double positionZ = telemetry == null ? null : telemetry.getPositionZ();
        GeoCoordinateService.GeoCoordinate coordinate = geoCoordinateService.fromLocal(
                positionX,
                positionY,
                positionZ
        );
        LocalDateTime telemetryAt = telemetry == null ? null : telemetry.getRecordedAt();

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
                positionX,
                positionY,
                positionZ,
                coordinate == null ? null : coordinate.latitude(),
                coordinate == null ? null : coordinate.longitude(),
                telemetry == null ? null : telemetry.getBatteryLevel(),
                0,
                telemetryAt,
                telemetry == null ? null : telemetry.getSource(),
                true,
                "UNKNOWN",
                false,
                null,
                "UNKNOWN",
                detail
        );
    }

    private static long ageSeconds(LocalDateTime timestamp, LocalDateTime now) {
        return timestamp == null ? -1 : Math.max(0, Duration.between(timestamp, now).getSeconds());
    }

    private static boolean isStale(LocalDateTime timestamp, LocalDateTime now, int staleSeconds) {
        return timestamp == null || ageSeconds(timestamp, now) > Math.max(1, staleSeconds);
    }

    private static Integer linkQuality(DeviceStatus status, long heartbeatAgeSeconds, int staleSeconds) {
        if (status != DeviceStatus.ONLINE || heartbeatAgeSeconds < 0) {
            return 0;
        }
        int window = Math.max(1, staleSeconds);
        double freshness = 1.0 - Math.min(1.0, heartbeatAgeSeconds / (double) window);
        return (int) Math.round(freshness * 100.0);
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
