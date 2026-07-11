package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "mission_event")
public class MissionEvent extends BaseEntity {

    @Column(name = "mission_id", nullable = false)
    private Long missionId;

    @Column(name = "run_id")
    private Long runId;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 40)
    private MissionEventType eventType;

    @Enumerated(EnumType.STRING)
    @Column(length = 40)
    private MissionStage stage;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MissionEventLevel level;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(length = 1000)
    private String message;

    @Column(length = 80)
    private String source;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    protected MissionEvent() {
    }

    public MissionEvent(Long missionId, MissionEventType eventType, String title, String message, String source) {
        this(missionId, null, eventType, null, MissionEventLevel.INFO, title, message, source);
    }

    public MissionEvent(
            Long missionId,
            Long runId,
            MissionEventType eventType,
            MissionStage stage,
            MissionEventLevel level,
            String title,
            String message,
            String source
    ) {
        this.missionId = missionId;
        this.runId = runId;
        this.eventType = eventType;
        this.stage = stage;
        this.level = level;
        this.title = title;
        this.message = message;
        this.source = source;
        this.occurredAt = LocalDateTime.now();
    }

    public Long getMissionId() {
        return missionId;
    }

    public Long getRunId() {
        return runId;
    }

    public MissionEventType getEventType() {
        return eventType;
    }

    public MissionStage getStage() {
        return stage;
    }

    public MissionEventLevel getLevel() {
        return level;
    }

    public String getTitle() {
        return title;
    }

    public String getMessage() {
        return message;
    }

    public String getSource() {
        return source;
    }

    public LocalDateTime getOccurredAt() {
        return occurredAt;
    }
}
