package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "mission_task_device")
public class MissionTaskDevice extends BaseEntity {

    @Column(name = "mission_id", nullable = false)
    private Long missionId;

    @Column(name = "device_id", nullable = false)
    private Long deviceId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private MissionDeviceRole role;

    @Column(name = "call_sign", length = 80)
    private String callSign;

    @Column(nullable = false)
    private boolean required;

    @Column(name = "assigned_at", nullable = false)
    private LocalDateTime assignedAt;

    @Column(length = 500)
    private String notes;

    protected MissionTaskDevice() {
    }

    public MissionTaskDevice(
            Long missionId,
            Long deviceId,
            MissionDeviceRole role,
            String callSign,
            boolean required,
            String notes
    ) {
        this.missionId = missionId;
        this.deviceId = deviceId;
        this.role = role;
        this.callSign = callSign;
        this.required = required;
        this.assignedAt = LocalDateTime.now();
        this.notes = notes;
    }

    public Long getMissionId() {
        return missionId;
    }

    public Long getDeviceId() {
        return deviceId;
    }

    public MissionDeviceRole getRole() {
        return role;
    }

    public String getCallSign() {
        return callSign;
    }

    public boolean isRequired() {
        return required;
    }

    public LocalDateTime getAssignedAt() {
        return assignedAt;
    }

    public String getNotes() {
        return notes;
    }
}
