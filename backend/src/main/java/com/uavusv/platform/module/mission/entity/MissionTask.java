package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "mission_task")
public class MissionTask extends BaseEntity {

    @Column(nullable = false, unique = true, length = 64)
    private String code;

    @Column(nullable = false, length = 120)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private MissionType type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private MissionStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private MissionStage stage;

    @Column(nullable = false)
    private Integer priority;

    @Column(name = "target_name", length = 120)
    private String targetName;

    @Column(name = "target_behavior", length = 255)
    private String targetBehavior;

    @Column(name = "mission_area", length = 255)
    private String missionArea;

    @Column(name = "planned_start_at")
    private LocalDateTime plannedStartAt;

    @Column(name = "planned_end_at")
    private LocalDateTime plannedEndAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @Column(length = 1000)
    private String description;

    @Column(nullable = false)
    private boolean deleted;

    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

    protected MissionTask() {
    }

    public MissionTask(String code) {
        this.code = code;
    }

    public void update(
            String code,
            String name,
            MissionType type,
            MissionStatus status,
            MissionStage stage,
            Integer priority,
            String targetName,
            String targetBehavior,
            String missionArea,
            LocalDateTime plannedStartAt,
            LocalDateTime plannedEndAt,
            String description
    ) {
        this.code = code;
        this.name = name;
        this.type = type;
        this.status = status;
        this.stage = stage;
        this.priority = priority;
        this.targetName = targetName;
        this.targetBehavior = targetBehavior;
        this.missionArea = missionArea;
        this.plannedStartAt = plannedStartAt;
        this.plannedEndAt = plannedEndAt;
        this.description = description;
    }

    public void softDelete() {
        this.deleted = true;
        this.deletedAt = LocalDateTime.now();
    }

    public void updateStatus(MissionStatus status, MissionStage stage) {
        this.status = status;
        this.stage = stage;
        if (status == MissionStatus.RUNNING && this.startedAt == null) {
            this.startedAt = LocalDateTime.now();
        }
        if (status == MissionStatus.COMPLETED || status == MissionStatus.CANCELLED || status == MissionStatus.FAILED) {
            this.completedAt = LocalDateTime.now();
        }
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public MissionType getType() {
        return type;
    }

    public MissionStatus getStatus() {
        return status;
    }

    public MissionStage getStage() {
        return stage;
    }

    public Integer getPriority() {
        return priority;
    }

    public String getTargetName() {
        return targetName;
    }

    public String getTargetBehavior() {
        return targetBehavior;
    }

    public String getMissionArea() {
        return missionArea;
    }

    public LocalDateTime getPlannedStartAt() {
        return plannedStartAt;
    }

    public LocalDateTime getPlannedEndAt() {
        return plannedEndAt;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public LocalDateTime getCompletedAt() {
        return completedAt;
    }

    public String getDescription() {
        return description;
    }

    public boolean isDeleted() {
        return deleted;
    }
}
