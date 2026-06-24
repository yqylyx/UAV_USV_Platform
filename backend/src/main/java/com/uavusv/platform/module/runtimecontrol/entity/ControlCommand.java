package com.uavusv.platform.module.runtimecontrol.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "control_command")
public class ControlCommand extends BaseEntity {
    @Column(name = "session_id")
    private Long sessionId;
    @Enumerated(EnumType.STRING)
    @Column(name = "command_type", nullable = false, length = 32)
    private CommandType commandType;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private CommandStatus status;
    @Column(name = "requested_by", length = 64)
    private String requestedBy;
    @Column(name = "requested_at", nullable = false)
    private LocalDateTime requestedAt;
    @Column(name = "completed_at")
    private LocalDateTime completedAt;
    @Column(length = 1000)
    private String detail;

    protected ControlCommand() {
    }

    public ControlCommand(Long sessionId, CommandType commandType, String requestedBy) {
        this.sessionId = sessionId;
        this.commandType = commandType;
        this.requestedBy = requestedBy;
        this.status = CommandStatus.PENDING;
        this.requestedAt = LocalDateTime.now();
    }

    public void succeed(String detail) {
        this.status = CommandStatus.SUCCEEDED;
        this.detail = detail;
        this.completedAt = LocalDateTime.now();
    }

    public void fail(String detail) {
        this.status = CommandStatus.FAILED;
        this.detail = detail;
        this.completedAt = LocalDateTime.now();
    }
}
