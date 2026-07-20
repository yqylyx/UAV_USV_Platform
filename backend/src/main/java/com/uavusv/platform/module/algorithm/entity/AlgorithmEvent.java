package com.uavusv.platform.module.algorithm.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "algorithm_event")
public class AlgorithmEvent extends BaseEntity {

    @Column(name = "command_id", length = 64)
    private String commandId;

    @Enumerated(EnumType.STRING)
    @Column(name = "algorithm_type", length = 32)
    private AlgorithmType algorithmType;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_level", nullable = false, length = 32)
    private AlgorithmEventLevel level;

    @Column(length = 64)
    private String stage;

    @Column(nullable = false, length = 1000)
    private String message;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    protected AlgorithmEvent() {
    }

    public AlgorithmEvent(String commandId, AlgorithmType algorithmType, AlgorithmEventLevel level, String stage, String message) {
        this.commandId = commandId;
        this.algorithmType = algorithmType;
        this.level = level == null ? AlgorithmEventLevel.INFO : level;
        this.stage = stage;
        this.message = message;
        this.occurredAt = LocalDateTime.now();
    }

    public String getCommandId() { return commandId; }
    public AlgorithmType getAlgorithmType() { return algorithmType; }
    public AlgorithmEventLevel getLevel() { return level; }
    public String getStage() { return stage; }
    public String getMessage() { return message; }
    public LocalDateTime getOccurredAt() { return occurredAt; }
}
