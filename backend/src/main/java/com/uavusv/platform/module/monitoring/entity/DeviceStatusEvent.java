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
@Table(name = "device_status_event")
public class DeviceStatusEvent extends BaseEntity {
    @Column(name = "device_id", nullable = false)
    private Long deviceId;
    @Enumerated(EnumType.STRING)
    @Column(name = "previous_status", length = 32)
    private DeviceStatus previousStatus;
    @Enumerated(EnumType.STRING)
    @Column(name = "current_status", nullable = false, length = 32)
    private DeviceStatus currentStatus;
    @Column(nullable = false, length = 32)
    private String source;
    @Column(length = 500)
    private String message;
    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    protected DeviceStatusEvent() {
    }

    public DeviceStatusEvent(Long deviceId, DeviceStatus previousStatus, DeviceStatus currentStatus,
                             String source, String message, LocalDateTime occurredAt) {
        this.deviceId = deviceId;
        this.previousStatus = previousStatus;
        this.currentStatus = currentStatus;
        this.source = source;
        this.message = message;
        this.occurredAt = occurredAt;
    }
}
