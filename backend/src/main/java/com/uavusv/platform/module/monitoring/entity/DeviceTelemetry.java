package com.uavusv.platform.module.monitoring.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "device_telemetry")
public class DeviceTelemetry extends BaseEntity {
    @Column(name = "device_id", nullable = false)
    private Long deviceId;
    @Column(name = "recorded_at", nullable = false)
    private LocalDateTime recordedAt;
    @Column(name = "sequence_no")
    private Long sequence;
    @Column(name = "position_x", nullable = false)
    private double positionX;
    @Column(name = "position_y", nullable = false)
    private double positionY;
    @Column(name = "position_z", nullable = false)
    private double positionZ;
    @Column(name = "orientation_x")
    private Double orientationX;
    @Column(name = "orientation_y")
    private Double orientationY;
    @Column(name = "orientation_z")
    private Double orientationZ;
    @Column(name = "orientation_w")
    private Double orientationW;

    protected DeviceTelemetry() {
    }

    public DeviceTelemetry(Long deviceId, LocalDateTime recordedAt, Long sequence, RuntimePose pose) {
        this.deviceId = deviceId;
        this.recordedAt = recordedAt;
        this.sequence = sequence;
        this.positionX = pose.positionX();
        this.positionY = pose.positionY();
        this.positionZ = pose.positionZ();
        this.orientationX = pose.orientationX();
        this.orientationY = pose.orientationY();
        this.orientationZ = pose.orientationZ();
        this.orientationW = pose.orientationW();
    }
}
