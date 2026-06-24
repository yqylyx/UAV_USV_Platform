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

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 40)
    private MissionEventType eventType;

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
        this.missionId = missionId;
        this.eventType = eventType;
        this.title = title;
        this.message = message;
        this.source = source;
        this.occurredAt = LocalDateTime.now();
    }

    public Long getMissionId() {
        return missionId;
    }

    public MissionEventType getEventType() {
        return eventType;
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
