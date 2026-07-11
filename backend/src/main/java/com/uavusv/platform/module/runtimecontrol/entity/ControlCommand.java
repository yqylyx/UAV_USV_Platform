package com.uavusv.platform.module.runtimecontrol.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "control_command")
public class ControlCommand extends BaseEntity {
    @Column(name = "session_id")
    private Long sessionId;
    @Column(name = "run_id")
    private Long runId;
    @Column(name = "device_id")
    private Long deviceId;
    @Column(name = "command_key", nullable = false, unique = true, length = 64)
    private String commandKey;
    @Column(name = "payload_json", columnDefinition = "TEXT")
    private String payload;
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
    @Column(name = "dispatched_at")
    private LocalDateTime dispatchedAt;
    @Column(name = "acknowledged_at")
    private LocalDateTime acknowledgedAt;
    @Column(name = "completed_at")
    private LocalDateTime completedAt;
    @Column(length = 1000)
    private String detail;
    @Column(name = "error_code", length = 64)
    private String errorCode;

    protected ControlCommand() {
    }

    public ControlCommand(Long sessionId, CommandType commandType, String requestedBy) {
        this(sessionId, null, null, commandType, null, requestedBy);
    }

    public ControlCommand(
            Long sessionId,
            Long runId,
            Long deviceId,
            CommandType commandType,
            String payload,
            String requestedBy
    ) {
        this.sessionId = sessionId;
        this.runId = runId;
        this.deviceId = deviceId;
        this.commandKey = UUID.randomUUID().toString();
        this.commandType = commandType;
        this.payload = payload;
        this.requestedBy = requestedBy;
        this.status = CommandStatus.PENDING;
        this.requestedAt = LocalDateTime.now();
    }

    public void succeed(String detail) {
        acknowledge(detail);
    }

    public void dispatch(String detail) {
        this.status = CommandStatus.DISPATCHED;
        this.detail = detail;
        this.dispatchedAt = LocalDateTime.now();
    }

    public void acknowledge(String detail) {
        this.status = CommandStatus.ACKNOWLEDGED;
        this.detail = detail;
        this.acknowledgedAt = LocalDateTime.now();
        this.completedAt = LocalDateTime.now();
    }

    public void fail(String detail) {
        fail("DISPATCH_FAILED", detail);
    }

    public void fail(String errorCode, String detail) {
        this.status = CommandStatus.FAILED;
        this.errorCode = errorCode;
        this.detail = detail;
        this.completedAt = LocalDateTime.now();
    }

    public void timeout(String detail) {
        this.status = CommandStatus.TIMEOUT;
        this.errorCode = "ACK_TIMEOUT";
        this.detail = detail;
        this.completedAt = LocalDateTime.now();
    }

    public Long getSessionId() {
        return sessionId;
    }

    public Long getRunId() { return runId; }
    public Long getDeviceId() { return deviceId; }
    public String getCommandKey() { return commandKey; }
    public String getPayload() { return payload; }

    public CommandType getCommandType() {
        return commandType;
    }

    public CommandStatus getStatus() {
        return status;
    }

    public String getRequestedBy() {
        return requestedBy;
    }

    public LocalDateTime getRequestedAt() {
        return requestedAt;
    }

    public LocalDateTime getDispatchedAt() { return dispatchedAt; }
    public LocalDateTime getAcknowledgedAt() { return acknowledgedAt; }

    public LocalDateTime getCompletedAt() {
        return completedAt;
    }

    public String getDetail() {
        return detail;
    }

    public String getErrorCode() { return errorCode; }
}
