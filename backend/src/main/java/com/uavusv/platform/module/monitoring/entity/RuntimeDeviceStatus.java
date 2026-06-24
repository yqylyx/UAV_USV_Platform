package com.uavusv.platform.module.monitoring.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "device_runtime_status")
public class RuntimeDeviceStatus extends BaseEntity {

    @Column(name = "device_id", nullable = false, unique = true)
    private Long deviceId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private DeviceStatus status;

    @Column(nullable = false, length = 32)
    private String source;

    @Column(name = "session_id")
    private Long sessionId;

    @Column(name = "instance_id", length = 128)
    private String instanceId;

    @Column(name = "last_heartbeat_at")
    private LocalDateTime lastHeartbeatAt;

    @Column(name = "last_message_at")
    private LocalDateTime lastMessageAt;

    @Column(name = "last_sequence")
    private Long lastSequence;

    @Column(length = 128)
    private String host;

    private Integer port;

    @Column(name = "position_x")
    private Double positionX;

    @Column(name = "position_y")
    private Double positionY;

    @Column(name = "position_z")
    private Double positionZ;

    @Column(name = "orientation_x")
    private Double orientationX;

    @Column(name = "orientation_y")
    private Double orientationY;

    @Column(name = "orientation_z")
    private Double orientationZ;

    @Column(name = "orientation_w")
    private Double orientationW;

    @Column(length = 500)
    private String detail;

    protected RuntimeDeviceStatus() {
    }

    public RuntimeDeviceStatus(Long deviceId) {
        this.deviceId = deviceId;
        this.status = DeviceStatus.UNKNOWN;
        this.source = "REGISTRY";
    }

    public void observe(String source, String instanceId, LocalDateTime observedAt, Long sequence,
                        String host, Integer port, RuntimePose pose, String detail) {
        this.status = DeviceStatus.ONLINE;
        this.source = source;
        this.instanceId = instanceId;
        this.lastHeartbeatAt = observedAt;
        this.lastMessageAt = observedAt;
        this.lastSequence = sequence;
        this.host = host;
        this.port = port;
        this.detail = detail;
        if (pose != null) {
            this.positionX = pose.positionX();
            this.positionY = pose.positionY();
            this.positionZ = pose.positionZ();
            this.orientationX = pose.orientationX();
            this.orientationY = pose.orientationY();
            this.orientationZ = pose.orientationZ();
            this.orientationW = pose.orientationW();
        }
    }

    public void markOffline(String detail) {
        this.status = DeviceStatus.OFFLINE;
        this.detail = detail;
    }

    public Long getDeviceId() { return deviceId; }
    public DeviceStatus getStatus() { return status; }
    public String getSource() { return source; }
    public Long getSessionId() { return sessionId; }
    public String getInstanceId() { return instanceId; }
    public LocalDateTime getLastHeartbeatAt() { return lastHeartbeatAt; }
    public LocalDateTime getLastMessageAt() { return lastMessageAt; }
    public Long getLastSequence() { return lastSequence; }
    public String getHost() { return host; }
    public Integer getPort() { return port; }
    public Double getPositionX() { return positionX; }
    public Double getPositionY() { return positionY; }
    public Double getPositionZ() { return positionZ; }
    public Double getOrientationX() { return orientationX; }
    public Double getOrientationY() { return orientationY; }
    public Double getOrientationZ() { return orientationZ; }
    public Double getOrientationW() { return orientationW; }
    public String getDetail() { return detail; }
}
